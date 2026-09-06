"""
La barre de progression, et surtout son silence.

Le test qui compte vraiment est `test_rien_n_est_ecrit_hors_terminal` :
`reproduce.py` capture la sortie de `evaluate.py` pour l'écrire dans
`evaluation-<modèle>.txt`, un fichier publiable. Une barre qui ne se tairait pas
hors terminal y déverserait des milliers de retours chariot.
"""

import io

from analyse_legislatives.utils.progress import progress_bar


def test_rien_n_est_ecrit_hors_terminal():
    stream = io.StringIO()  # isatty() est faux
    with progress_bar(10, "Simulation", stream=stream) as tick:
        for i in range(10):
            tick(i + 1, 10)
    assert stream.getvalue() == ""


def test_la_barre_se_ferme_meme_sur_exception():
    stream = io.StringIO()
    try:
        with progress_bar(4, "Simulation", stream=stream, enabled=True):
            raise RuntimeError("échec au milieu")
    except RuntimeError:
        pass
    assert stream.getvalue().endswith("\n")


def test_un_total_nul_ne_divise_pas_par_zero():
    stream = io.StringIO()
    with progress_bar(0, "Vide", stream=stream, enabled=True) as tick:
        tick(0, 0)
    assert "0/0" in stream.getvalue()
