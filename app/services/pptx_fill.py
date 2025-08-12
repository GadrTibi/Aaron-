from typing import Dict, Optional, List, Tuple
from pptx import Presentation
from pptx.util import Inches

def _walk_shapes(shapes):
    for sh in shapes:
        yield sh
        if hasattr(sh, "shapes"):
            for sub in _walk_shapes(sh.shapes):
                yield sub

def _find_shape_by_name(prs, shape_name: str):
    for slide in prs.slides:
        for sh in _walk_shapes(slide.shapes):
            try:
                if (sh.name or "").strip() == shape_name:
                    return sh, slide
            except Exception:
                pass
    return None, None

def _rebuild_index(paragraph) -> tuple[str, list[tuple[int,int]]]:
    segs, parts = [], []
    for i, r in enumerate(paragraph.runs):
        t = r.text or ""
        parts.append(t)
        segs.append((i, len(t)))
    return ("".join(parts), segs)

def _locate_in_runs(segs, start_pos: int, end_pos: int):
    pos = 0
    s_run = s_off = e_run = e_off = 0
    for idx, ln in segs:
        if start_pos >= pos and start_pos <= pos + ln:
            s_run = idx; s_off = start_pos - pos; break
        pos += ln
    pos = 0
    for idx, ln in segs:
        if end_pos > pos and end_pos <= pos + ln:
            e_run = idx; e_off = end_pos - pos; break
        pos += ln
    return s_run, s_off, e_run, e_off

def _replace_token_in_paragraph(paragraph, token: str, value: str) -> bool:
    changed = False
    while True:
        combined, segs = _rebuild_index(paragraph)
        idx = combined.find(token)
        if idx < 0: break
        start, end = idx, idx + len(token)
        s_run, s_off, e_run, e_off = _locate_in_runs(segs, start, end)
        style_run = paragraph.runs[s_run]

        pre = style_run.text[:s_off]
        style_run.text = pre + value

        for ridx in range(s_run + 1, e_run):
            paragraph.runs[ridx].text = ""
        if e_run != s_run:
            last = paragraph.runs[e_run]
            suffix = last.text[e_off:]
            last.text = suffix
        changed = True
    return changed

def replace_text_preserving_style(shapes, mapping: Dict[str, str]) -> None:
    for shape in _walk_shapes(shapes):
        if hasattr(shape, "text_frame") and shape.text_frame:
            for para in shape.text_frame.paragraphs:
                for token, value in mapping.items():
                    _replace_token_in_paragraph(para, token, value)

def insert_image(slide, image_path: str, left=Inches(1), top=Inches(3), width=Inches(8)) -> None:
    slide.shapes.add_picture(image_path, left, top, width=width)

def replace_image_by_shape_name(prs, shape_name: str, image_path: str):
    target = None; target_slide = None
    for slide in prs.slides:
        for sh in _walk_shapes(slide.shapes):
            try:
                if (sh.name or '').strip() == shape_name:
                    target = sh; target_slide = slide; break
            except Exception:
                continue
        if target: break
    if not target: return False
    try:
        left = target.left; top = target.top; width = target.width; height = target.height
        sp = target._element; sp.getparent().remove(sp)
        target_slide.shapes.add_picture(image_path, left, top, width=width, height=height)
        return True
    except Exception:
        return False

def fill_shape_with_picture_by_name(prs, shape_name: str, image_path: str) -> bool:
    """
    Remplit un AutoShape existant avec une image, SANS le supprimer,
    pour conserver le masque (ex. cercle).
    """
    sh, _ = _find_shape_by_name(prs, shape_name)
    if not sh:
        return False
    try:
        sh.fill.user_picture(image_path)
        # sécurité :
        try:
            sh.fill.transparency = 0
        except Exception:
            pass
        return True
    except Exception:
        return False

def generate_estimation_pptx(template_path: str, output_path: str, mapping: Dict[str, str], chart_image: Optional[str]=None, image_by_shape: Optional[Dict[str, str]]=None) -> None:
    prs = Presentation(template_path)
    for slide in prs.slides:
        replace_text_preserving_style(slide.shapes, mapping)

    target_slide = None
    for slide in prs.slides:
        texts = []
        for sh in _walk_shapes(slide.shapes):
            if hasattr(sh, "text_frame") and sh.text_frame:
                texts.append(sh.text_frame.text or "")
        text = "\n".join(texts)
        if "Vos revenus" in text or "vos revenus" in text.lower():
            target_slide = slide; break
    if target_slide is None: target_slide = prs.slides[-1]
    if chart_image: insert_image(target_slide, chart_image)
    if image_by_shape:
        for shape_name, img_path in image_by_shape.items():
            if not img_path:
                continue
            ok = False
            if shape_name.endswith("_MASK"):
                ok = fill_shape_with_picture_by_name(prs, shape_name, img_path)
            if not ok:
                replace_image_by_shape_name(prs, shape_name, img_path)
    prs.save(output_path)