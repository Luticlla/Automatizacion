"""Borra y vuelve a cargar las bases SQLite desde los CSV de datos/."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app import db


def main():
    cargado = db.reiniciar_proceso1()
    print(
        "var/proceso1.db cargada: "
        f"{cargado.get('agenda', 0)} filas de agenda, "
        f"{cargado.get('kits', 0)} kits, "
        f"{cargado.get('citas', 0)} citas semilla."
    )
    cargado2 = db.reiniciar_proceso2()
    print(
        "var/proceso2.db cargada: "
        f"{cargado2.get('tarifario', 0)} servicios de tarifario, "
        f"{cargado2.get('politicas', 0)} politicas comerciales."
    )


if __name__ == "__main__":
    main()
