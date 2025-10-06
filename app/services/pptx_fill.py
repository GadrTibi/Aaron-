import logging
import os
import re
from typing import Dict, Optional, List, Tuple

from pptx import Presentation
from pptx.util import Inches
from PIL import Image

from app.services.pptx_images import inject_tagged_image

LOGGER = logging.getLogger(__name__)


def _walk_shapes(shapes):
    """Yield all shapes recursively, diving into groups."""
    for sh in shapes:
        yield sh
        # If the shape is a group, dive into its children and yield them too
        if hasattr(sh, "shapes"):
            for sub in _walk_shapes(sh.shapes):
                yield sub


def insert_plot_into_pptx(template_path: str, output_path: str, image_path: str) -> None:
    """Insert the histogram image into slide 6 using the dedicated mask shape."""

    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Fichier PPTX introuvable: {template_path}")
    if not os.path.exists(image_path):
        raise FileNotFoundError(
            f"Image d'histogramme introuvable: {image_path}. Générez le graphique avant l'export."
        )

    prs = Presentation(template_path)
    if len(prs.slides) <= 5:
        raise ValueError("La présentation ne contient pas de slide 6 pour y insérer l'histogramme.")

    slide = prs.slides[5]

    def _is_mask(name: Optional[str]) -> bool:
        if not name:
            return False
        norm = name.strip()
        if not norm:
            return False
        if norm.lower() == "estimation_histo_mask":
            return True
        return re.match(r"(?i).*histo.*-?mask$", norm) is not None

    target_shape = None
    for sh in _walk_shapes(slide.shapes):
        if _is_mask(getattr(sh, "name", None)):
            target_shape = sh
            break

    if target_shape is None:
        raise ValueError(
            "Shape mask introuvable en slide 6 (attendu: 'ESTIMATION_HISTO_MASK' ou variante '*histo*-mask')."
        )

    left, top, width, height = target_shape.left, target_shape.top, target_shape.width, target_shape.height

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    slide.shapes.add_picture(image_path, left, top, width=width, height=height)
    LOGGER.info("Histogramme inséré dans la slide 6 (%s)", getattr(target_shape, "name", ""))
    prs.save(output_path)

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


def replace_image_by_shape_name(prs, shape_name: str, image_path: str) -> bool:
    """Remplace une image en la retrouvant par son nom."""
    try:
        ext = os.path.splitext(image_path)[1].lower()
        if ext not in (".jpg", ".jpeg", ".png"):
            tmp_path = os.path.splitext(image_path)[0] + ".png"
            with Image.open(image_path) as img:
                img.save(tmp_path, "PNG")
            image_path = tmp_path
    except Exception:
        pass

    for slide in prs.slides:
        for sh in _walk_shapes(slide.shapes):
            try:
                if (sh.name or "").strip() == shape_name:
                    left, top, width, height = sh.left, sh.top, sh.width, sh.height
                    try:
                        sp = sh.element
                        sp.getparent().remove(sp)
                    except Exception:
                        pass
                    slide.shapes.add_picture(image_path, left, top, width=width, height=height)
                    print(f"[OK] Image remplacée dans {shape_name}")
                    return True
            except Exception:
                continue

    print(f"[WARN] Shape {shape_name} introuvable dans le PPTX.")
    return False

def generate_estimation_pptx(template_path: str, output_path: str, mapping: Dict[str, str], chart_image: Optional[str]=None, image_by_shape: Optional[Dict[str, str]]=None) -> None:
    prs = Presentation(template_path)
    for slide in prs.slides:
        replace_text_preserving_style(slide.shapes, mapping)
    if image_by_shape:
        for shape_name, img_path in image_by_shape.items():
            if not img_path:
                continue
            # MAP_MASK doit toujours être injectée en plein rectangle sans masque
            if shape_name == "MAP_MASK":
                replace_image_by_shape_name(prs, shape_name, img_path)
            # VISITE_1_MASK et VISITE_2_MASK conservent l'injection avec masque circulaire
            elif shape_name in ("VISITE_1_MASK", "VISITE_2_MASK"):
                inject_tagged_image(prs, shape_name, img_path)
            else:
                replace_image_by_shape_name(prs, shape_name, img_path)
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    prs.save(output_path)

    if chart_image:
        insert_plot_into_pptx(output_path, output_path, chart_image)


def generate_book_pptx(template_path: str, output_path: str, mapping: Dict[str, str], image_by_shape: Optional[Dict[str, str]] = None) -> None:
    """Generate a Book PPTX from template and mapping/images."""
    prs = Presentation(template_path)
    for slide in prs.slides:
        replace_text_preserving_style(slide.shapes, mapping)

    if image_by_shape:
        for shape_name, img_path in image_by_shape.items():
            if not img_path:
                continue
            if shape_name in ("MAP_BOOK_MASK", "BOOK_MAP_MASK"):
                # Always replace the shape by the map image (full rectangle)
                replace_image_by_shape_name(prs, shape_name, img_path)
            elif shape_name in (
                "PORTE_ENTREE_MASK",
                "ENTREE_MASK",
                "APPARTEMENT_MASK",
                # Anciennes conventions
                "BOOK_ACCESS_PHOTO_PORTE",
                "BOOK_ACCESS_PHOTO_ENTREE",
                "BOOK_ACCESS_PHOTO_APPART",
            ):
                # Try native mask injection first, fallback to rectangle replace
                ok = inject_tagged_image(prs, shape_name, img_path)
                if not ok:
                    replace_image_by_shape_name(prs, shape_name, img_path)
            else:
                replace_image_by_shape_name(prs, shape_name, img_path)
    prs.save(output_path)
