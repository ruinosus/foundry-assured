from fastapi import APIRouter

from app.shared.telemetry import configured as telemetry_configured

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str | bool]:
    # `telemetry` diz se os spans `gen_ai.*` estão REALMENTE saindo para o Application Insights.
    # Sem isto, ligada e desligada têm a mesma aparência: o log de `setup_telemetry` sai em INFO,
    # que não chega ao stdout sob o uvicorn, e a única forma de saber era abrir o portal e
    # esperar. Um booleano aqui responde na hora, e é o mesmo estado que o `lifespan` decidiu.
    return {"status": "ok", "telemetry": telemetry_configured()}
