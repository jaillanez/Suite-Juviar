"""Género del postulante: el que dice el CV o, si no lo dice, el que sugiere el nombre de pila.

Siempre se informa de dónde salió, para que RRHH sepa cuándo es una deducción.
"""

from __future__ import annotations

import re
import unicodedata

FEMENINO = "F"
MASCULINO = "M"
OTRO = "X"  # no binario u otro, tal como lo declara el postulante

# Nombres de pila frecuentes en Argentina que no siguen la regla de la terminación,
# más los más comunes de cada género para no depender sólo de la regla.
_FEMENINOS = set("""
abigail agustina ailen aime aldana alejandra alicia alma ambar ana andrea angeles antonella
araceli ariadna ayelen azul barbara beatriz belen brenda candela carla carmen carolina catalina
cecilia celeste clara claudia constanza cristina daiana dalma daniela debora delfina denise
diana dolores elena eliana elizabeth emilia estefania ester estela eugenia evelyn fabiana
fatima fernanda flor florencia gabriela gimena gisela gladys graciela guadalupe ines irene
isabel ivana jaquelin jazmin jesica johana josefina juana julia juliana julieta karen karina
laura lidia liliana lorena lourdes lucia lucila luciana ludmila luz magali maite malena
marcela margarita maria mariana maricel marina marisa marisol marta martina mercedes micaela
milagros miriam monica nadia natalia nelida noelia nora norma olga paola patricia paula
pilar priscila raquel rocio romina rosa rosana rosario ruth sabrina sandra sara silvana silvia
sofia solange soledad susana tamara teresa valentina valeria vanesa veronica victoria
viviana ximena yamila yanina yesica zoe abril isabella mia emma olivia lola renata nahiara
milena jimena noemi ines raquel beatriz luz pilar carmen rocio mercedes dolores consuelo
ester ruth miriam edith judith lilian karen evelyn jaquelin nicole michelle denise ivon
""".split())  # noqa: SIM905 - lista larga, más legible como texto

_MASCULINOS = set("""
adrian agustin alan alberto alejandro alexis alfredo alvaro andres angel anibal antonio ariel
armando arturo augusto axel benjamin bautista bruno camilo carlos cesar cristian damian
daniel dante dario david diego eduardo elias emanuel emiliano enrique ernesto esteban ezequiel
facundo federico felipe fernando francisco franco gabriel gaston gerardo german gonzalo
guillermo gustavo hector hernan horacio hugo ignacio ivan jaime javier jeremias joaquin jonathan
jorge jose juan julian julio kevin leandro leonardo leonel lisandro lorenzo lucas luciano
luis manuel marcelo marcos mariano mario martin matias mauricio maximiliano miguel milton
nahuel nestor nicolas norberto oscar pablo patricio pedro ramiro ramon raul ricardo roberto
rodrigo rogelio roman ruben salvador santiago santino sebastian sergio simon thiago tobias
tomas ulises valentin victor walter ezequiel lautaro mateo benicio luca joaquin gael noah
elian bastian ian liam dylan isaac josue moises jesus luka borja nehuen
""".split())  # noqa: SIM905 - lista larga, más legible como texto

# Terminados en «a» que son de varón, y terminados en «o» o consonante que son de mujer.
_EXCEPCIONES_MASCULINAS = {"luca", "luka", "bautista", "nicola", "joshua", "elia", "kalua"}
_EXCEPCIONES_FEMENINAS = {"consuelo", "rocio", "amparo", "socorro", "rosario", "ines", "raquel",
                          "isabel", "maribel", "abigail", "beatriz", "luz", "carmen", "mercedes",
                          "dolores", "pilar", "ruth", "ester", "miriam", "edith", "judith", "lilian",
                          "karen", "evelyn", "nicole", "michelle", "denise", "ivon", "noemi",
                          "zoe", "ailen", "ayelen", "belen", "jazmin", "flor", "maricel", "marisol",
                          "solange", "gladys", "jaquelin", "elizabeth", "sol", "ambar", "aime"}

_EXPLICITO = {
    "f": FEMENINO, "femenino": FEMENINO, "mujer": FEMENINO, "fem": FEMENINO,
    "m": MASCULINO, "masculino": MASCULINO, "hombre": MASCULINO, "varon": MASCULINO, "masc": MASCULINO,
    "x": OTRO, "otro": OTRO, "otra": OTRO, "nobinario": OTRO,
}


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z ]", " ", sin_tildes.lower()).split())


def genero_explicito(valor: object) -> str | None:
    """«Femenino», «M», «Mujer»… tal como lo escribió el postulante."""
    if not isinstance(valor, str):
        return None
    texto = _normalizar(valor).replace("no binario", "nobinario")
    # Se quita la etiqueta («Sexo: F», «Género: femenino») y lo que queda tiene que ser
    # exactamente un valor conocido; una palabra suelta en medio de otra frase no cuenta.
    texto = re.sub(r"^(?:sexo|genero)\s*", "", texto).strip()
    return _EXPLICITO.get(texto)


def genero_por_nombre(nombre_completo: object) -> str | None:
    """Deduce por el primer nombre de pila; None si no hay forma razonable de saberlo."""
    if not isinstance(nombre_completo, str):
        return None
    for palabra in _normalizar(nombre_completo).split():
        if palabra in _FEMENINOS or palabra in _EXCEPCIONES_FEMENINAS:
            return FEMENINO
        if palabra in _MASCULINOS or palabra in _EXCEPCIONES_MASCULINAS:
            return MASCULINO
        if len(palabra) > 2:
            # El primer nombre que no está en las listas decide por su terminación.
            if palabra.endswith("a"):
                return FEMENINO
            if palabra.endswith("o"):
                return MASCULINO
            return None
    return None


def genero_de(ficha: dict[str, object] | None) -> dict[str, str | None]:
    """{"genero": "F" | "M" | "X" | None, "origen": "CV" | "NOMBRE" | None}."""
    ficha = ficha or {}
    declarado = ficha.get("genero")
    if isinstance(declarado, str) and declarado.strip():
        # El postulante dijo algo: nunca se reemplaza por una deducción, aunque no se entienda.
        return {"genero": genero_explicito(declarado), "origen": "CV"}
    if deducido := genero_por_nombre(ficha.get("nombre_completo")):
        return {"genero": deducido, "origen": "NOMBRE"}
    return {"genero": None, "origen": None}
