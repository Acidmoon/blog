use std::path::PathBuf;
use std::sync::Arc;

use axum::{
    body::Bytes,
    extract::{DefaultBodyLimit, Path as AxumPath, Query, State},
    http::{header, StatusCode},
    response::{Html, IntoResponse, Json, Response},
};
use chrono::Utc;
use multer::{self, Constraints, Multipart, SizeLimit};
use serde_json::json;
use uuid::Uuid;

use crate::db::Database;
use crate::models::{self, Book, BookListQuery};
use crate::reader;

pub struct AppState {
    pub db: Database,
    pub books_dir: PathBuf,
    pub covers_dir: PathBuf,
}

pub type SharedState = Arc<AppState>;

// ── GET /api/books ────────────────────────────────────
pub async fn list_books(
    State(state): State<SharedState>,
    Query(query): Query<BookListQuery>,
) -> Result<Json<Vec<Book>>, StatusCode> {
    let books = state
        .db
        .list_books(query.format.as_deref(), query.q.as_deref())
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    Ok(Json(books))
}

// ── GET /api/books/:id ────────────────────────────────
pub async fn get_book(
    State(state): State<SharedState>,
    AxumPath(id): AxumPath<i64>,
) -> Result<Json<Book>, StatusCode> {
    let book = state
        .db
        .get_book(id)
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
        .ok_or(StatusCode::NOT_FOUND)?;
    Ok(Json(book))
}

// ── GET /api/books/:id/read ───────────────────────────
pub async fn read_book(
    State(state): State<SharedState>,
    AxumPath(id): AxumPath<i64>,
) -> Result<Response, StatusCode> {
    let book = state
        .db
        .get_book(id)
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
        .ok_or(StatusCode::NOT_FOUND)?;

    match book.format.as_str() {
        "txt" | "md" => {
            let file_path = state.books_dir.join(&book.storage_key);
            let html = reader::render_text_to_html(&file_path, &book.format)
                .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
            Ok(Html(html).into_response())
        }
        "html" => {
            let file_path = state.books_dir.join(&book.storage_key);
            let content =
                std::fs::read_to_string(&file_path).map_err(|_| StatusCode::NOT_FOUND)?;
            Ok(Html(content).into_response())
        }
        "pdf" | "epub" => {
            // These are handled client-side; return book info as JSON
            Ok(Json(json!({
                "format": book.format,
                "file_url": format!("/api/books/{}/file", book.id),
                "title": book.title,
            }))
            .into_response())
        }
        _ => Err(StatusCode::UNSUPPORTED_MEDIA_TYPE),
    }
}

// ── GET /api/books/:id/file (download) ────────────────
pub async fn download_book(
    State(state): State<SharedState>,
    AxumPath(id): AxumPath<i64>,
) -> Result<Response, StatusCode> {
    let book = state
        .db
        .get_book(id)
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
        .ok_or(StatusCode::NOT_FOUND)?;

    // Increment download count
    let _ = state.db.increment_download(id);

    let file_path = state.books_dir.join(&book.storage_key);
    if !file_path.exists() {
        return Err(StatusCode::NOT_FOUND);
    }

    let content_type = reader::content_type(&book.file_name);
    let data = tokio::fs::read(&file_path).await.map_err(|_| StatusCode::NOT_FOUND)?;

    let headers = [
        (header::CONTENT_TYPE, content_type),
        (
            header::CONTENT_DISPOSITION,
            &format!("attachment; filename=\"{}\"", book.file_name),
        ),
    ];

    Ok((headers, data).into_response())
}

// ── GET /api/books/:id/view (inline, for reader embed) ──
pub async fn view_book(
    State(state): State<SharedState>,
    AxumPath(id): AxumPath<i64>,
) -> Result<Response, StatusCode> {
    let book = state
        .db
        .get_book(id)
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
        .ok_or(StatusCode::NOT_FOUND)?;

    // Do NOT increment download count for view

    let file_path = state.books_dir.join(&book.storage_key);
    if !file_path.exists() {
        return Err(StatusCode::NOT_FOUND);
    }

    let content_type = reader::content_type(&book.file_name);
    let data = tokio::fs::read(&file_path).await.map_err(|_| StatusCode::NOT_FOUND)?;

    let headers = [
        (header::CONTENT_TYPE, content_type),
        (header::CONTENT_DISPOSITION, "inline"),
        (header::CACHE_CONTROL, "public, max-age=3600"),
    ];

    Ok((headers, data).into_response())
}

// ── POST /api/books (upload) ──────────────────────────
pub async fn upload_book(
    State(state): State<SharedState>,
    headers: axum::http::HeaderMap,
    body: Bytes,
) -> Result<Json<serde_json::Value>, (StatusCode, String)> {
    let content_type = headers
        .get(header::CONTENT_TYPE)
        .and_then(|v| v.to_str().ok())
        .ok_or_else(|| (StatusCode::BAD_REQUEST, "缺少 Content-Type".to_string()))?;

    let boundary = multer::parse_boundary(content_type)
        .map_err(|e| (StatusCode::BAD_REQUEST, format!("无效的 multipart: {}", e)))?;

    let constraints = Constraints::new()
        .size_limit(SizeLimit::new().whole_stream(100 * 1024 * 1024));

    let cursor = body.as_ref();
    let mut multipart = Multipart::with_reader_with_constraints(cursor, boundary, constraints);

    let mut title = String::new();
    let mut author = String::new();
    let mut description = String::new();
    let mut file_data: Option<(String, Vec<u8>)> = None;
    let mut cover_data: Option<(String, Vec<u8>)> = None;
    let mut user_title = false;
    let mut user_author = false;

    while let Ok(Some(mut field)) = multipart.next_field().await {
        let name = field.name().unwrap_or("").to_string();
        match name.as_str() {
            "title" => {
                if let Ok(val) = field.text().await {
                    let trimmed = val.trim().to_string();
                    if !trimmed.is_empty() {
                        title = trimmed;
                        user_title = true;
                    }
                }
            }
            "author" => {
                if let Ok(val) = field.text().await {
                    let trimmed = val.trim().to_string();
                    if !trimmed.is_empty() {
                        author = trimmed;
                        user_author = true;
                    }
                }
            }
            "description" => {
                if let Ok(val) = field.text().await {
                    description = val.trim().to_string();
                }
            }
            "file" => {
                let file_name = field.file_name().unwrap_or("unknown").to_string();
                match field.bytes().await {
                    Ok(data) if !data.is_empty() => {
                        file_data = Some((file_name, data.to_vec()));
                    }
                    Ok(_) => {
                        file_data = Some((file_name, Vec::new()));
                    }
                    Err(e) => {
                        return Err((StatusCode::BAD_REQUEST, format!("读取文件失败: {}", e)));
                    }
                }
            }
            "cover" => {
                let cover_name = field.file_name().map(|s| s.to_string()).unwrap_or_default();
                if let Ok(data) = field.bytes().await {
                    if !data.is_empty() && !cover_name.is_empty() {
                        cover_data = Some((cover_name, data.to_vec()));
                    }
                }
            }
            _ => {}
        }
    }

    let (file_name, file_bytes) = file_data.ok_or_else(|| {
        (StatusCode::BAD_REQUEST, "请上传文件".to_string())
    })?;

    let format = models::detect_format(&file_name);
    if format == "unknown" {
        return Err((
            StatusCode::BAD_REQUEST,
            format!("不支持的文件格式: {}", file_name),
        ));
    }
    if file_bytes.len() as u64 > models::MAX_FILE_SIZE {
        return Err((StatusCode::BAD_REQUEST, "文件过大（最大 100MB）".to_string()));
    }

    let storage_key = format!("{}.{}", Uuid::new_v4(), std::path::Path::new(&file_name)
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("dat"));

    // Write file to disk first (needed for metadata extraction)
    let dest = state.books_dir.join(&storage_key);
    tokio::fs::write(&dest, &file_bytes)
        .await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, format!("写入文件失败: {}", e)))?;

    // Handle user-uploaded cover
    let mut cover_path = String::new();
    if let Some((cover_name, cover_bytes)) = cover_data {
        let cover_ext = std::path::Path::new(&cover_name)
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or("jpg");
        let cover_key = format!("{}.{}", Uuid::new_v4(), cover_ext);
        let cover_dest = state.covers_dir.join(&cover_key);
        if let Ok(_) = tokio::fs::write(&cover_dest, &cover_bytes).await {
            cover_path = format!("/covers/{}", cover_key);
        }
    }

    // Auto-detect metadata from PDF/EPUB (run in blocking thread pool)
    if (format == "pdf" || format == "epub") && (!user_title || !user_author || cover_path.is_empty()) {
        let dest_clone = dest.clone();
        let covers_clone = state.covers_dir.clone();
        let fmt_clone = format.clone();
        let extract_result = tokio::task::spawn_blocking(move || {
            extract_metadata(&dest_clone, &covers_clone, &fmt_clone)
        }).await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, format!("元数据提取任务失败: {}", e)))?;

        if let Ok((meta_title, meta_author, meta_cover)) = extract_result {
            if !user_title && !meta_title.is_empty() {
                title = meta_title;
            }
            if !user_author && !meta_author.is_empty() {
                author = meta_author;
            }
            if cover_path.is_empty() && !meta_cover.is_empty() {
                cover_path = meta_cover;
                tracing::info!("自动提取封面: {}", cover_path);
            }
        } else if let Err(e) = &extract_result {
            // 提取失败不影响上传，只是跳过自动识别
            tracing::warn!("元数据提取跳过: {}", e);
        }
    }

    // Validate title (still required after auto-detection)
    if title.trim().is_empty() {
        // Clean up saved file
        let _ = std::fs::remove_file(&dest);
        return Err((StatusCode::BAD_REQUEST, "标题不能为空，且自动识别未提取到标题。请手动填写。".to_string()));
    }

    let now = Utc::now().format("%Y-%m-%d %H:%M:%S").to_string();
    let book = Book {
        id: 0,
        title: title.trim().to_string(),
        author: author.trim().to_string(),
        format: format.to_string(),
        file_name,
        storage_key,
        file_size: file_bytes.len() as i64,
        cover_path,
        description: description.trim().to_string(),
        uploaded_at: now,
        download_count: 0,
    };

    let id = state
        .db
        .insert_book(&book)
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, format!("数据库写入失败: {}", e)))?;

    Ok(Json(json!({"id": id, "success": true})))
}

fn extract_metadata(file_path: &std::path::Path, covers_dir: &std::path::Path, format: &str) -> Result<(String, String, String), String> {
    let script_path = {
        let manifest_dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        manifest_dir.join("extract_metadata.py")
    };
    let file_path = file_path.to_path_buf();
    let covers_dir = covers_dir.to_path_buf();
    let fmt = format.to_string();

    // Run synchronously - this is already wrapped in spawn_blocking by caller
    let output = std::process::Command::new("/usr/bin/python3")
        .arg(&script_path)
        .arg(&file_path)
        .arg(&covers_dir)
        .arg(&fmt)
        .output()
        .map_err(|e| format!("执行提取脚本失败: {} (PATH可能找不到python3)", e))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        // Don't fail the whole upload - just return empty strings
        if !stderr.trim().is_empty() {
            tracing::warn!("元数据提取脚本stderr: {}", stderr);
        }
        return Ok((String::new(), String::new(), String::new()));
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    match serde_json::from_str::<serde_json::Value>(&stdout) {
        Ok(result) => Ok((
            result["title"].as_str().unwrap_or("").to_string(),
            result["author"].as_str().unwrap_or("").to_string(),
            result["cover_path"].as_str().unwrap_or("").to_string(),
        )),
        Err(e) => {
            tracing::warn!("元数据提取结果解析失败: {} (输出: {})", e, stdout);
            Ok((String::new(), String::new(), String::new()))
        }
    }
}

// ── DELETE /api/books/:id ─────────────────────────────
pub async fn delete_book(
    State(state): State<SharedState>,
    AxumPath(id): AxumPath<i64>,
) -> Result<Json<serde_json::Value>, StatusCode> {
    let book = state
        .db
        .get_book(id)
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
        .ok_or(StatusCode::NOT_FOUND)?;

    // Delete file
    let file_path = state.books_dir.join(&book.storage_key);
    let _ = std::fs::remove_file(&file_path);
    // Delete cover if exists
    if !book.cover_path.is_empty() {
        let cover_file = book.cover_path.trim_start_matches("/covers/");
        let cover_path = state.covers_dir.join(cover_file);
        let _ = std::fs::remove_file(&cover_path);
    }

    state
        .db
        .delete_book(id)
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    Ok(Json(json!({"success": true})))
}

// ── Serve frontend pages ──────────────────────────────
fn frontend_html(name: &str) -> Result<Response, StatusCode> {
    use axum::response::IntoResponse;
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("static")
        .join(name);
    let content = std::fs::read_to_string(&path).map_err(|_| StatusCode::NOT_FOUND)?;
    Ok((
        [("Cache-Control", "no-cache, no-store, must-revalidate")],
        Html(content),
    ).into_response())
}

pub async fn index_page() -> Result<Response, StatusCode> {
    frontend_html("index.html")
}

pub async fn reader_page() -> Result<Response, StatusCode> {
    frontend_html("reader.html")
}

pub async fn admin_page() -> Result<Response, StatusCode> {
    frontend_html("admin.html")
}
