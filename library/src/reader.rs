use std::path::Path;

/// Read a text file and convert to HTML for inline reading.
/// Supports TXT (wrapped in <pre>) and Markdown (rendered via comrak).
pub fn render_text_to_html(path: &Path, format: &str) -> Result<String, String> {
    let content = std::fs::read_to_string(path)
        .map_err(|e| format!("读取文件失败: {}", e))?;

    match format {
        "md" | "markdown" => {
            let mut options = comrak::Options::default();
            options.extension.table = true;
            options.extension.strikethrough = true;
            options.extension.autolink = true;
            options.render.unsafe_ = true; // allow embedded HTML
            let html = comrak::markdown_to_html(&content, &options);
            Ok(format!(
                r#"<div class="md-reader article-body">{}</div>"#,
                html
            ))
        }
        "txt" => {
            let escaped = html_escape(&content);
            Ok(format!(
                r#"<pre class="txt-reader">{}</pre>"#,
                escaped
            ))
        }
        _ => Err(format!("不支持的阅读格式: {}", format)),
    }
}

/// Get file extension for content-type
pub fn content_type(filename: &str) -> &'static str {
    let lower = filename.to_lowercase();
    if lower.ends_with(".pdf") {
        "application/pdf"
    } else if lower.ends_with(".epub") {
        "application/epub+zip"
    } else if lower.ends_with(".mobi") {
        "application/x-mobipocket-ebook"
    } else if lower.ends_with(".txt") {
        "text/plain; charset=utf-8"
    } else if lower.ends_with(".md") || lower.ends_with(".markdown") {
        "text/markdown; charset=utf-8"
    } else if lower.ends_with(".html") || lower.ends_with(".htm") {
        "text/html; charset=utf-8"
    } else {
        "application/octet-stream"
    }
}

fn html_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}
