from typing import Dict, Optional, List, Tuple
from pptx import Presentation
from pptx.util import Inches


def _walk_shapes(shapes):
    """Yield all shapes recursively, diving into groups."""
    for sh in shapes:
        yield sh
        # If the shape is a group, dive into its children and yield them too
        if hasattr(sh, "shapes"):
            for sub in _walk_shapes(sh.shapes):
                yield sub

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


def inject_masked_image(prs, shape_name: str, image_path: str) -> bool:
    """
    Recherche récursivement la forme par son nom dans toutes les diapos et groupes,
    et remplit son fond avec l'image fournie sans supprimer la forme,
    pour conserver le masque rond.
    Retourne True si l'injection a réussi, False sinon.
    """
    import os
    import tempfile
    from PIL import Image

    target = None
    for slide in prs.slides:
        for sh in _walk_shapes(slide.shapes):
            try:
                if (sh.name or "").strip() == shape_name:
                    target = sh
                    break
            except Exception:
                continue
        if target:
            break
    if not target:
        print(f"[WARN] Shape {shape_name} introuvable dans le PPTX.")
        return False

    tmp_path = None
    try:
        ext = os.path.splitext(image_path)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg"):
            with Image.open(image_path) as img:
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                img.save(tmp.name, format="PNG")
                tmp_path = tmp.name
                image_path = tmp.name

        target.fill.user_picture(image_path)
        try:
            target.fill.transparency = 0
        except Exception:
            pass
        print(f"[OK] Image injectée dans {shape_name}")
        return True
    except Exception as e:
        print(f"[WARN] Impossible d'injecter l'image dans {shape_name}: {e}")
        return False
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

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
            target_slide = slide
            break
    if target_slide is None:
        target_slide = prs.slides[-1]
    if chart_image:
        insert_image(target_slide, chart_image)
    if image_by_shape:
        for shape_name in ("VISITE_1_MASK", "VISITE_2_MASK"):
            img_path = image_by_shape.get(shape_name)
            if img_path:
                inject_masked_image(prs, shape_name, img_path)
    prs.save(output_path)
