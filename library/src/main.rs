mod db;
mod models;
mod reader;
mod routes;

use std::path::PathBuf;
use std::sync::Arc;

use axum::{
    extract::DefaultBodyLimit,
    routing::{get, delete},
    Router,
};
use tower_http::services::ServeDir;
use tower_http::cors::{Any, CorsLayer};
use tracing_subscriber::EnvFilter;

use crate::routes::AppState;

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::try_from_default_env().unwrap_or_else(|_| "info".into()))
        .init();

    // Data directories
    let data_dir = PathBuf::from(
        std::env::var("LIBRARY_DATA_DIR").unwrap_or_else(|_| "/root/blog/data/books".into()),
    );
    let books_dir = data_dir.clone();
    let covers_dir = data_dir.join("covers");
    let db_path = data_dir.join("library.db");

    std::fs::create_dir_all(&books_dir).expect("创建图书目录失败");
    std::fs::create_dir_all(&covers_dir).expect("创建封面目录失败");

    let database = db::Database::open(&db_path).expect("数据库初始化失败");

    let state = Arc::new(AppState {
        db: database,
        books_dir,
        covers_dir,
    });

    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);

    let app = Router::new()
        // API routes
        .route("/api/books", get(routes::list_books).post(routes::upload_book))
        .route("/api/books/{id}", get(routes::get_book).delete(routes::delete_book))
        .route("/api/books/{id}/read", get(routes::read_book))
        .route("/api/books/{id}/file", get(routes::download_book))
        .route("/api/books/{id}/view", get(routes::view_book))
        // Frontend pages
        .route("/", get(routes::index_page))
        .route("/reader", get(routes::reader_page))
        .route("/admin", get(routes::admin_page))
        // Static files
        .nest_service(
            "/static",
            ServeDir::new(
                PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("static"),
            ),
        )
        .nest_service(
            "/covers",
            ServeDir::new(
                state.covers_dir.clone(),
            ),
        )
        .layer(DefaultBodyLimit::max(100 * 1024 * 1024)) // 100MB for upload
        .layer(cors)
        .with_state(state);

    let port = std::env::var("LIBRARY_PORT").unwrap_or_else(|_| "8085".into());
    let addr = format!("0.0.0.0:{}", port);
    tracing::info!("Library service starting on {}", addr);

    let listener = tokio::net::TcpListener::bind(&addr)
        .await
        .expect("绑定端口失败");

    axum::serve(listener, app)
        .await
        .expect("服务器启动失败");
}
