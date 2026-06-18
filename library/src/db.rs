use anyhow::{Context, Result};
use rusqlite::{params, Connection};
use std::path::Path;
use std::sync::Mutex;

use crate::models::Book;

pub struct Database {
    conn: Mutex<Connection>,
}

impl Database {
    pub fn open(db_path: &Path) -> Result<Self> {
        if let Some(parent) = db_path.parent() {
            std::fs::create_dir_all(parent).context("创建数据库目录失败")?;
        }
        let conn = Connection::open(db_path).context("打开数据库失败")?;
        conn.execute_batch("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;")
            .context("设置 pragma 失败")?;
        conn.execute_batch(
            "CREATE TABLE IF NOT EXISTS books (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                author      TEXT NOT NULL DEFAULT '',
                format      TEXT NOT NULL,
                file_name   TEXT NOT NULL,
                storage_key TEXT NOT NULL UNIQUE,
                file_size   INTEGER NOT NULL DEFAULT 0,
                cover_path  TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                uploaded_at TEXT NOT NULL,
                download_count INTEGER NOT NULL DEFAULT 0
            );",
        )
        .context("建表失败")?;
        Ok(Database {
            conn: Mutex::new(conn),
        })
    }

    pub fn list_books(&self, format_filter: Option<&str>, search: Option<&str>) -> Result<Vec<Book>> {
        let conn = self.conn.lock().unwrap();
        let mut sql = String::from(
            "SELECT id, title, author, format, file_name, storage_key, file_size, cover_path, description, uploaded_at, download_count FROM books WHERE 1=1",
        );
        let mut param_values: Vec<String> = vec![];

        if let Some(fmt) = format_filter {
            param_values.push(fmt.to_string());
            sql.push_str(&format!(" AND format = ?{}", param_values.len()));
        }
        if let Some(q) = search {
            let like = format!("%{}%", q);
            param_values.push(like);
            sql.push_str(&format!(
                " AND (title LIKE ?{} OR author LIKE ?{} OR description LIKE ?{})",
                param_values.len(),
                param_values.len(),
                param_values.len()
            ));
        }
        sql.push_str(" ORDER BY uploaded_at DESC");

        let mut stmt = conn.prepare(&sql).context("查询准备失败")?;
        let params_refs: Vec<&dyn rusqlite::types::ToSql> =
            param_values.iter().map(|v| v as &dyn rusqlite::types::ToSql).collect();

        let rows = stmt
            .query_map(params_refs.as_slice(), |row| {
                Ok(Book {
                    id: row.get(0)?,
                    title: row.get(1)?,
                    author: row.get(2)?,
                    format: row.get(3)?,
                    file_name: row.get(4)?,
                    storage_key: row.get(5)?,
                    file_size: row.get(6)?,
                    cover_path: row.get(7)?,
                    description: row.get(8)?,
                    uploaded_at: row.get(9)?,
                    download_count: row.get(10)?,
                })
            })
            .context("查询执行失败")?;

        let mut books = Vec::new();
        for row in rows {
            books.push(row.context("读取行失败")?);
        }
        Ok(books)
    }

    pub fn get_book(&self, id: i64) -> Result<Option<Book>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn
            .prepare(
                "SELECT id, title, author, format, file_name, storage_key, file_size, cover_path, description, uploaded_at, download_count FROM books WHERE id = ?1",
            )
            .context("查询准备失败")?;
        let mut rows = stmt
            .query_map(params![id], |row| {
                Ok(Book {
                    id: row.get(0)?,
                    title: row.get(1)?,
                    author: row.get(2)?,
                    format: row.get(3)?,
                    file_name: row.get(4)?,
                    storage_key: row.get(5)?,
                    file_size: row.get(6)?,
                    cover_path: row.get(7)?,
                    description: row.get(8)?,
                    uploaded_at: row.get(9)?,
                    download_count: row.get(10)?,
                })
            })
            .context("查询执行失败")?;
        match rows.next() {
            Some(row) => Ok(Some(row.context("读取行失败")?)),
            None => Ok(None),
        }
    }

    pub fn insert_book(&self, book: &Book) -> Result<i64> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "INSERT INTO books (title, author, format, file_name, storage_key, file_size, cover_path, description, uploaded_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
            params![
                book.title,
                book.author,
                book.format,
                book.file_name,
                book.storage_key,
                book.file_size,
                book.cover_path,
                book.description,
                book.uploaded_at,
            ],
        )
        .context("插入失败")?;
        Ok(conn.last_insert_rowid())
    }

    pub fn increment_download(&self, id: i64) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "UPDATE books SET download_count = download_count + 1 WHERE id = ?1",
            params![id],
        )
        .context("更新下载计数失败")?;
        Ok(())
    }

    pub fn delete_book(&self, id: i64) -> Result<bool> {
        let conn = self.conn.lock().unwrap();
        let affected = conn
            .execute("DELETE FROM books WHERE id = ?1", params![id])
            .context("删除失败")?;
        Ok(affected > 0)
    }

    pub fn update_cover_path(&self, id: i64, cover_path: &str) -> Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "UPDATE books SET cover_path = ?1 WHERE id = ?2",
            params![cover_path, id],
        )
        .context("更新封面路径失败")?;
        Ok(())
    }
}
