"""CommonMark to a small DOM vocabulary; document text never becomes executable HTML."""
from pathlib import Path, PureWindowsPath
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
from skill_ui.contracts import UIError

MAX_IMAGE_BYTES = 20 * 1024 * 1024
TAGS = frozenset(('p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'ul', 'ol', 'li',
                  'strong', 'em', 's', 'table', 'thead', 'tbody', 'tr', 'th', 'td'))
PARSER = MarkdownIt('commonmark', {'html': False, 'maxNesting': 32}).enable(['table', 'strikethrough'])
IMAGE_TYPES = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
               '.gif': 'image/gif', '.webp': 'image/webp'}


def image_path(document, destination):
    """Only references within this registered document's directory grant image access."""
    try:
        url = urlsplit(destination)
        if url.scheme or url.netloc:
            raise UIError('image', '仅预览文档目录内的本地图片；远程图片未加载。')
        relative = unquote(url.path)
        if (not relative or relative.startswith(('/', '\\')) or PureWindowsPath(relative).drive
                or ':' in relative or any(ord(char) < 32 for char in relative)):
            raise UIError('image', '图片路径必须是文档目录内的相对路径。')
        root = document.parent
        source = root / relative.replace('\\', '/')
        path = source.resolve()
        if not path.is_relative_to(root):
            raise UIError('image', '图片超出文档目录，未加载。')
        path = source.resolve(strict=True)
        if not path.is_file() or path.suffix.lower() not in IMAGE_TYPES:
            raise UIError('image', '不支持此图片格式；支持 PNG、JPEG、GIF、WebP。')
        return source, path, IMAGE_TYPES[path.suffix.lower()]
    except (OSError, ValueError, RuntimeError):
        raise UIError('image', '图片不存在或无法读取。') from None


def image_signature(header, mime):
    return {'image/png': header.startswith(b'\x89PNG\r\n\x1a\n'),
            'image/jpeg': header.startswith(b'\xff\xd8\xff'),
            'image/gif': header[:6] in (b'GIF87a', b'GIF89a'),
            'image/webp': header[:4] == b'RIFF' and header[8:12] == b'WEBP'}.get(mime, False)


def safe_link(href):
    try:
        url = urlsplit(href)
        if url.scheme.lower() in ('http', 'https') and url.netloc:
            return href
    except ValueError:
        pass
    return None


def nodes(text, resolve_image):
    """Use the same parse for display and attachment discovery, including reference images."""
    budget = 12000

    def convert(tokens):
        nonlocal budget
        result, stack = [], []
        current = result
        for token in tokens:
            budget -= 1
            if budget < 0:
                raise UIError('markdown', '文档结构过多，请下载原文件查看。')
            if token.type == 'inline':
                current.extend(convert(token.children or []))
            elif token.nesting == -1:
                if stack:
                    current = stack.pop()
            elif token.nesting == 1:
                tag = token.tag if token.tag in TAGS else 'span'
                node = {'tag': tag, 'children': []}
                if token.type == 'link_open':
                    href = safe_link(token.attrGet('href') or '')
                    node.update(tag='a' if href else 'span')
                    if href:
                        node['href'] = href
                    else:
                        node['title'] = '此链接未开放；可下载文档后查看。'
                if token.tag == 'ol' and token.attrGet('start'):
                    node['start'] = int(token.attrGet('start'))
                current.append(node)
                stack.append(current)
                current = node['children']
            elif token.type == 'image':
                alt = PARSER.renderer.renderInlineAsText(token.children or [], PARSER.options, {})
                node = {'tag': 'img', 'alt': alt, 'title': token.attrGet('title') or ''}
                try:
                    node['resource'] = resolve_image(token.attrGet('src') or '')
                except UIError as error:
                    node['error'] = str(error)
                current.append(node)
            elif token.type in ('fence', 'code_block'):
                current.append({'tag': 'pre', 'children': [{'tag': 'code', 'text': token.content}]})
            elif token.type == 'code_inline':
                current.append({'tag': 'code', 'text': token.content})
            elif token.type in ('hr', 'hardbreak'):
                current.append({'tag': 'hr' if token.type == 'hr' else 'br'})
            else:
                current.append({'text': '\n' if token.type == 'softbreak' else token.content})
        return result

    return convert(PARSER.parse(text))
