import math
import sys
import time

import matplotlib.pyplot as plt
import numpy as np
from mpi4py import MPI


class droite:
    def __init__(self, p1, p2):
        self.a = p2[1] - p1[1]
        self.b = -p2[0] + p1[0]
        self.c = p1[1] * p2[0] - p1[0] * p2[1]

    def meme_cote(self, q1, q2) -> bool:
        return (self.a * q1[0] + self.b * q1[1] + self.c) * (self.a * q2[0] + self.b * q2[1] + self.c) > 0


def calcul_enveloppe(nuage_de_points: np.ndarray) -> np.ndarray:
    enveloppe = []
    lst_nuage = list(nuage_de_points[:])
    # Recherche du point appartenant au nuage ayant l'ordonnée la plus basse.
    lst_nuage.sort(key=lambda coord: coord[1])
    bas = lst_nuage.pop(0)
    # Ce point appartient forcément à l'enveloppe convexe !
    enveloppe.append(bas)

    # On trie le reste du nuage en fonction des angles formés par la droite parallèle à l'abscisse et passant
    # par bas avec la droite reliant bas avec le point considéré
    lst_nuage.sort(key=lambda coord: math.atan2(coord[1] - bas[1], coord[0] - bas[0]))

    # On replace le point le plus bas à la fin de la liste des points du nuage
    lst_nuage.append(bas)

    # Tant qu'il y a des points dans le nuage...
    while len(lst_nuage) > 0:
        # Puisque le premier point a l'angle minimal, il appartient à l'enveloppe :
        enveloppe.append(lst_nuage.pop(0))

        # Tant qu'il y a au moins quatre points dans l'enveloppe...
        while len(enveloppe) >= 4:
            if not droite(enveloppe[-3], enveloppe[-2]).meme_cote(enveloppe[-4], enveloppe[-1]):
                enveloppe.pop(-2)
            else:
                break
    return np.array(enveloppe)


taille_nuage: int = 55440
nbre_repet: int = 3
resolution_x: int = 1_000
resolution_y: int = 1_000

# Génération d'un nuage de points

elapsed_generation: float = 0.
elapsed_convexhull: float = 0.

if len(sys.argv) > 1:
    taille_nuage = int(sys.argv[1])
if len(sys.argv) > 2:
    nbre_repet = int(sys.argv[2])

enveloppe = None
nuage_local = None
point_pb = np.array([[191.49137204, -999.9999561], [191.94755935, -999.90181187], [192.30030105, -999.61773124],
                     [194.54076141, -996.75667377]])


def pprint(*args, **kwargs):
    print("[%03d]" % rank, *args, **kwargs)


comm = MPI.COMM_WORLD
rank = comm.Get_rank()
size = comm.Get_size()
if rank == 0:
    print()

# on répartit la génération pour avoir autant de points par processus
local_range = range(rank * taille_nuage // size, (rank + 1) * taille_nuage // size)
if rank == size - 1:
    local_range = range(rank * taille_nuage // size, taille_nuage)

for r in range(nbre_repet):
    # on crée la partie du nuage pour chaque processus
    t1 = time.time()
    nuage_local = np.array(np.array([[resolution_x * i * math.cos(48371. * i) / taille_nuage for i in local_range],
                                     [resolution_y * math.sin(50033. / (i + 1.)) for i in local_range]],
                                    dtype=np.float64).T)
    t2 = time.time()
    elapsed_generation += t2 - t1

    # Calcul de l'enveloppe convexe :
    t1 = time.time()
    local_enveloppe = calcul_enveloppe(nuage_local)
    t2 = time.time()
    elapsed_convexhull += t2 - t1

    merged_enveloppe = None
    if rank == 0:
        comm.isend(local_enveloppe, dest=1)
        other_local_enveloppe = comm.recv(source=1)
        merged_enveloppe = np.concatenate((local_enveloppe, other_local_enveloppe), axis=0)
    elif rank == 1:
        comm.isend(local_enveloppe, dest=0)
        other_local_enveloppe = comm.recv(source=0)
        merged_enveloppe = np.concatenate((local_enveloppe, other_local_enveloppe), axis=0)

    # il semblerait que des points de l'enveloppe sont perdus ici. Je n'ai pas reussi à corriger ce
    # bug
    t1 = time.time()
    enveloppe = calcul_enveloppe(merged_enveloppe)
    t2 = time.time()
    elapsed_convexhull += t2 - t1

pprint(f"Temps pris pour la generation d'un nuage de points : {elapsed_generation / nbre_repet}")
pprint(f"Temps pris pour le calcul de l'enveloppe convexe : {elapsed_convexhull / nbre_repet}")
pprint(f"Temps total : {sum((elapsed_generation, elapsed_convexhull)) / nbre_repet}")

# on reconstruit le nuage complet pour l'affichage
nuage = comm.gather(nuage_local, root=0)

if rank == 0:
    # on le reformat en une np array
    nuage = np.concatenate(nuage, axis=0)
    # affichage du nuage :
    plt.scatter(nuage[:, 0], nuage[:, 1])
    for i in range(len(enveloppe[:]) - 1):
        plt.plot([enveloppe[i, 0], enveloppe[i + 1, 0]], [enveloppe[i, 1], enveloppe[i + 1, 1]], 'bo', linestyle="-")
    plt.show()

    # validation de non-regression :
    if taille_nuage == 55440:
        ref = np.loadtxt("enveloppe_convexe_55440.ref")

        try:
            np.testing.assert_allclose(ref, enveloppe)
            pprint("Verification pour 55440 points: OK")
        except AssertionError as e:
            pprint(e)
            pprint("Verification pour 55440 points: FAILED")

pprint("Bye")
