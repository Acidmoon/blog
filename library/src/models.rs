use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Book {
    pub id: i64,
    pub title: String,
    pub author: String,
    pub format: String,
    pub file_name: String,
    pub storage_key: String,
    pub file_size: i64,
    pub cover_path: String,
    pub description: String,
    pub uploaded_at: String,
    pub download_count: i64,
}

#[derive(Debug, Deserialize)]
pub struct BookListQuery {
    pub format: Option<String>,
    pub q: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct UploadForm {
    pub title: String,
    pub author: Option<String>,
    pub description: Option<String>,
}

/// Detect file format from extension
pub fn detect_format(filename: &str) -> &'static str {
    let lower = filename.to_lowercase();
    if lower.ends_with(".pdf") {
        "pdf"
    } else if lower.ends_with(".epub") {
        "epub"
    } else if lower.ends_with(".mobi") {
        "mobi"
    } else if lower.ends_with(".txt") {
        "txt"
    } else if lower.ends_with(".md") || lower.ends_with(".markdown") {
        "md"
    } else if lower.ends_with(".html") || lower.ends_with(".htm") {
        "html"
    } else {
        "unknown"
    }
}

pub const ALLOWED_FORMATS: &[&str] = &["pdf", "epub", "mobi", "txt", "md", "html"];
pub const MAX_FILE_SIZE: u64 = 100 * 1024 * 1024; // 100MB
