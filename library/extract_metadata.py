#!/usr/bin/env python3
"""
Extract metadata (title, author) and first-page cover from PDF/EPUB files.
Usage: python3 extract_metadata.py <file_path> <covers_dir> <format>
Output: JSON to stdout
"""
import json
import os
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

def extract_pdf(file_path, covers_dir):
    """Extract metadata and first-page cover from PDF."""
    import fitz  # PyMuPDF
    doc = fitz.open(file_path)
    
    # Extract metadata
    meta = doc.metadata
    title = meta.get("title", "").strip()
    author = meta.get("author", "").strip()
    
    # Extract first page as cover image
    cover_path = ""
    if len(doc) > 0:
        page = doc[0]
        # Try 2x resolution for good quality, but not too large
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        # Save to temp then move
        cover_filename = os.path.splitext(os.path.basename(file_path))[0] + "_cover.png"
        cover_dest = os.path.join(covers_dir, cover_filename)
        # Make sure we don't overwrite
        counter = 1
        while os.path.exists(cover_dest):
            cover_filename = os.path.splitext(os.path.basename(file_path))[0] + f"_cover_{counter}.png"
            cover_dest = os.path.join(covers_dir, cover_filename)
            counter += 1
        pix.save(cover_dest)
        cover_path = f"/covers/{cover_filename}"
    
    doc.close()
    return title, author, cover_path


def extract_epub(file_path, covers_dir):
    """Extract metadata and cover from EPUB."""
    title = ""
    author = ""
    cover_path = ""
    
    with zipfile.ZipFile(file_path, 'r') as z:
        # Find container.xml
        try:
            container_xml = z.read("META-INF/container.xml")
        except KeyError:
            return title, author, cover_path
        
        # Parse container.xml to find OPF file
        root = ET.fromstring(container_xml)
        ns = {
            'c': 'urn:oasis:names:tc:opendocument:xmlns:container',
        }
        rootfiles = root.findall('.//c:rootfile', ns)
        if not rootfiles:
            return title, author, cover_path
        
        opf_path = rootfiles[0].get('full-path', '')
        
        # Read OPF file
        opf_content = z.read(opf_path)
        opf_dir = os.path.dirname(opf_path)
        
        # Parse OPF
        opf_root = ET.fromstring(opf_content)
        # Try different namespace patterns
        ns_opf = ''
        for tag in opf_root.tag.split('}'):
            if tag.startswith('http'):
                ns_opf = '{' + tag + '}'
                break
        
        def find_text(parent, tag):
            el = parent.find(f'{ns_opf}{tag}')
            if el is None:
                # Try without namespace
                el = parent.find(tag)
            if el is not None and el.text:
                return el.text.strip()
            return ''
        
        # Find metadata - try different structures
        metadata = opf_root.find(f'{ns_opf}metadata') or opf_root.find('metadata')
        if metadata is not None:
            # Dublin Core metadata
            dc_ns = '{http://purl.org/dc/elements/1.1/}'
            for child in metadata:
                tag = child.tag
                if tag == f'{dc_ns}title' and child.text:
                    title = child.text.strip()
                elif tag == f'{dc_ns}creator' and child.text:
                    author = child.text.strip()
                    # Take the first creator as author
                    if author:
                        pass
        
        # Find cover image from OPF manifest
        manifest = opf_root.find(f'{ns_opf}manifest') or opf_root.find('manifest')
        cover_id = None
        
        if metadata is not None:
            # Look for meta with name="cover"
            for child in metadata:
                meta_name = child.get('name', '')
                meta_content = child.get('content', '')
                if meta_name.lower() == 'cover':
                    cover_id = meta_content
        
        if manifest is not None and cover_id:
            for child in manifest:
                if child.get('id') == cover_id:
                    href = child.get('href', '')
                    if href:
                        cover_href = os.path.join(opf_dir, href)
                        try:
                            cover_data = z.read(cover_href)
                            # Save cover
                            ext = os.path.splitext(href)[1] or '.jpg'
                            cover_filename = os.path.splitext(os.path.basename(file_path))[0] + "_cover" + ext
                            cover_dest = os.path.join(covers_dir, cover_filename)
                            counter = 1
                            while os.path.exists(cover_dest):
                                cover_filename = os.path.splitext(os.path.basename(file_path))[0] + f"_cover_{counter}" + ext
                                cover_dest = os.path.join(covers_dir, cover_filename)
                                counter += 1
                            with open(cover_dest, 'wb') as f:
                                f.write(cover_data)
                            cover_path = f"/covers/{cover_filename}"
                        except (KeyError, OSError):
                            pass
        elif manifest is not None:
            # Try to find cover by common id patterns
            for child in manifest:
                cid = child.get('id', '').lower()
                if 'cover' in cid:
                    href = child.get('href', '')
                    properties = child.get('properties', '')
                    if href and ('cover-image' in properties or 'cover' in cid):
                        cover_href = os.path.join(opf_dir, href)
                        try:
                            cover_data = z.read(cover_href)
                            ext = os.path.splitext(href)[1] or '.jpg'
                            cover_filename = os.path.splitext(os.path.basename(file_path))[0] + "_cover" + ext
                            cover_dest = os.path.join(covers_dir, cover_filename)
                            counter = 1
                            while os.path.exists(cover_dest):
                                cover_filename = os.path.splitext(os.path.basename(file_path))[0] + f"_cover_{counter}" + ext
                                cover_dest = os.path.join(covers_dir, cover_filename)
                                counter += 1
                            with open(cover_dest, 'wb') as f:
                                f.write(cover_data)
                            cover_path = f"/covers/{cover_filename}"
                        except (KeyError, OSError):
                            pass
    
    return title, author, cover_path


def main():
    if len(sys.argv) < 4:
        print(json.dumps({"title": "", "author": "", "cover_path": ""}))
        return
    
    file_path = sys.argv[1]
    covers_dir = sys.argv[2]
    fmt = sys.argv[3].lower()
    
    if not os.path.exists(file_path):
        print(json.dumps({"title": "", "author": "", "cover_path": ""}))
        return
    
    os.makedirs(covers_dir, exist_ok=True)
    
    title = ""
    author = ""
    cover_path = ""
    
    if fmt == "pdf":
        title, author, cover_path = extract_pdf(file_path, covers_dir)
    elif fmt == "epub":
        title, author, cover_path = extract_epub(file_path, covers_dir)
    
    print(json.dumps({"title": title, "author": author, "cover_path": cover_path}))


if __name__ == "__main__":
    main()
