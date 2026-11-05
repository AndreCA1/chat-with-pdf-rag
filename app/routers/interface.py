from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.config import STATIC_DIR

router = APIRouter()

# A interface só carrega arquivos próprios, o que limita o impacto de um XSS.
INTERFACE_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


@router.get("/", include_in_schema=False)
def interface():
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Content-Security-Policy": INTERFACE_CSP},
    )
