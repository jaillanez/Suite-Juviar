from fastapi import APIRouter, Depends

from .dependencias import SesionActual, exigir_permiso

router = APIRouter(
    prefix="/sesion",
    tags=["sesión"],
    dependencies=[Depends(exigir_permiso("suite.acceder"))],
)


@router.get("")
def sesion_actual(sesion: SesionActual):
    return {
        "actor": sesion.actor,
        "empresa": sesion.empresa,
        "permisos": sorted(sesion.permisos),
        "identidad_simulada": sesion.identidad_simulada,
    }
