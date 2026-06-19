"""
world_cup_squads.py — Plantillas del Mundial 2026 con jugadores clave.
Datos basados en convocatorias confirmadas FIFA 2026.
Cada jugador tiene: impacto_base (0-100), posición, edad, descripción de forma.
"""

# Impacto base = potencial de influencia en el partido.
# Se ajusta dinámicamente por estadísticas del torneo.

SQUADS: dict[str, dict] = {

    "ARGENTINA": {
        "ranking_fifa": 1, "entrenador": "Lionel Scaloni",
        "estilo": "presión alta, juego combinativo, contraataque",
        "fortaleza": "mediocampo creativo, solidez defensiva",
        "debilidad": "dependencia de Messi, defensa ante velocidad",
        "jugadores": [
            {"nombre": "Lionel Messi",       "pos": "CAM", "edad": 38, "impacto": 99, "dorsal": 10},
            {"nombre": "Lautaro Martínez",   "pos": "ST",  "edad": 27, "impacto": 91, "dorsal": 22},
            {"nombre": "Rodrigo De Paul",    "pos": "CM",  "edad": 30, "impacto": 86, "dorsal": 7},
            {"nombre": "Alexis Mac Allister","pos": "CM",  "edad": 25, "impacto": 88, "dorsal": 20},
            {"nombre": "Ángel Di María",     "pos": "RW",  "edad": 36, "impacto": 82, "dorsal": 11},
            {"nombre": "Nicolás Otamendi",   "pos": "CB",  "edad": 36, "impacto": 78, "dorsal": 19},
            {"nombre": "Lisandro Martínez",  "pos": "CB",  "edad": 26, "impacto": 85, "dorsal": 25},
            {"nombre": "Emiliano Martínez",  "pos": "GK",  "edad": 32, "impacto": 89, "dorsal": 23},
            {"nombre": "Nicolás González",   "pos": "LW",  "edad": 26, "impacto": 80, "dorsal": 21},
            {"nombre": "Thiago Almada",      "pos": "CM",  "edad": 23, "impacto": 75, "dorsal": 18},
            {"nombre": "Paulo Dybala",       "pos": "CAM", "edad": 30, "impacto": 83, "dorsal": 21},
        ],
    },

    "BRAZIL": {
        "ranking_fifa": 5, "entrenador": "Carlo Ancelotti",
        "estilo": "fútbol posicional, ataque de posición, pressing",
        "fortaleza": "extremos de elite, creación de juego",
        "debilidad": "irregularidad defensiva, dependencia de Vinicius",
        "jugadores": [
            {"nombre": "Vinicius Jr",        "pos": "LW",  "edad": 24, "impacto": 97, "dorsal": 7},
            {"nombre": "Rodrygo",            "pos": "RW",  "edad": 23, "impacto": 88, "dorsal": 11},
            {"nombre": "Endrick",            "pos": "ST",  "edad": 18, "impacto": 84, "dorsal": 9},
            {"nombre": "Bruno Guimarães",    "pos": "CM",  "edad": 27, "impacto": 87, "dorsal": 5},
            {"nombre": "Casemiro",           "pos": "DM",  "edad": 32, "impacto": 82, "dorsal": 5},
            {"nombre": "Marquinhos",         "pos": "CB",  "edad": 29, "impacto": 83, "dorsal": 4},
            {"nombre": "Militão",            "pos": "CB",  "edad": 26, "impacto": 84, "dorsal": 3},
            {"nombre": "Alisson",            "pos": "GK",  "edad": 32, "impacto": 88, "dorsal": 1},
            {"nombre": "Raphinha",           "pos": "RW",  "edad": 27, "impacto": 84, "dorsal": 10},
            {"nombre": "Savinho",            "pos": "LW",  "edad": 20, "impacto": 77, "dorsal": 20},
            {"nombre": "Gerson",             "pos": "CM",  "edad": 27, "impacto": 74, "dorsal": 8},
        ],
    },

    "FRANCE": {
        "ranking_fifa": 2, "entrenador": "Didier Deschamps",
        "estilo": "transición rápida, solidez defensiva",
        "fortaleza": "profundidad de plantilla, físico, versatilidad táctica",
        "debilidad": "cohesión ofensiva, dependencia de velocistas",
        "jugadores": [
            {"nombre": "Kylian Mbappé",      "pos": "ST",  "edad": 26, "impacto": 98, "dorsal": 10},
            {"nombre": "Antoine Griezmann",  "pos": "CAM", "edad": 33, "impacto": 87, "dorsal": 7},
            {"nombre": "Ousmane Dembélé",    "pos": "RW",  "edad": 27, "impacto": 85, "dorsal": 11},
            {"nombre": "N'Golo Kanté",       "pos": "DM",  "edad": 33, "impacto": 84, "dorsal": 13},
            {"nombre": "Aurélien Tchouaméni","pos": "DM",  "edad": 24, "impacto": 86, "dorsal": 8},
            {"nombre": "William Saliba",     "pos": "CB",  "edad": 23, "impacto": 84, "dorsal": 17},
            {"nombre": "Dayot Upamecano",    "pos": "CB",  "edad": 26, "impacto": 80, "dorsal": 4},
            {"nombre": "Mike Maignan",       "pos": "GK",  "edad": 29, "impacto": 86, "dorsal": 16},
            {"nombre": "Marcus Thuram",      "pos": "ST",  "edad": 26, "impacto": 83, "dorsal": 9},
            {"nombre": "Eduardo Camavinga",  "pos": "CM",  "edad": 22, "impacto": 82, "dorsal": 14},
            {"nombre": "Jules Koundé",       "pos": "RB",  "edad": 26, "impacto": 80, "dorsal": 5},
        ],
    },

    "SPAIN": {
        "ranking_fifa": 3, "entrenador": "Luis de la Fuente",
        "estilo": "posesión, presión alta, toque corto",
        "fortaleza": "dominio del balón, generación joven, profundidad en mediocampo",
        "debilidad": "falta de delantero centro de elite",
        "jugadores": [
            {"nombre": "Rodri",              "pos": "DM",  "edad": 28, "impacto": 95, "dorsal": 16},
            {"nombre": "Pedri",              "pos": "CM",  "edad": 22, "impacto": 91, "dorsal": 8},
            {"nombre": "Gavi",               "pos": "CM",  "edad": 20, "impacto": 88, "dorsal": 6},
            {"nombre": "Lamine Yamal",       "pos": "RW",  "edad": 17, "impacto": 93, "dorsal": 19},
            {"nombre": "Nico Williams",      "pos": "LW",  "edad": 22, "impacto": 88, "dorsal": 11},
            {"nombre": "Morata",             "pos": "ST",  "edad": 31, "impacto": 78, "dorsal": 7},
            {"nombre": "Ferran Torres",      "pos": "FWD", "edad": 24, "impacto": 77, "dorsal": 9},
            {"nombre": "Unai Simón",         "pos": "GK",  "edad": 27, "impacto": 80, "dorsal": 1},
            {"nombre": "Pau Cubarsí",        "pos": "CB",  "edad": 17, "impacto": 78, "dorsal": 24},
            {"nombre": "Aymeric Laporte",    "pos": "CB",  "edad": 30, "impacto": 79, "dorsal": 14},
            {"nombre": "Dani Carvajal",      "pos": "RB",  "edad": 32, "impacto": 81, "dorsal": 2},
        ],
    },

    "ENGLAND": {
        "ranking_fifa": 4, "entrenador": "Lee Carsley",
        "estilo": "juego directo, balones largos, contraataque",
        "fortaleza": "individualidades de elite en ataque",
        "debilidad": "presión en torneos, penaltis históricos",
        "jugadores": [
            {"nombre": "Jude Bellingham",    "pos": "CM",  "edad": 21, "impacto": 95, "dorsal": 10},
            {"nombre": "Harry Kane",         "pos": "ST",  "edad": 31, "impacto": 93, "dorsal": 9},
            {"nombre": "Phil Foden",         "pos": "CAM", "edad": 24, "impacto": 89, "dorsal": 11},
            {"nombre": "Bukayo Saka",        "pos": "RW",  "edad": 22, "impacto": 90, "dorsal": 7},
            {"nombre": "Declan Rice",        "pos": "DM",  "edad": 25, "impacto": 88, "dorsal": 4},
            {"nombre": "Marcus Rashford",    "pos": "LW",  "edad": 26, "impacto": 81, "dorsal": 11},
            {"nombre": "Jordan Pickford",    "pos": "GK",  "edad": 30, "impacto": 80, "dorsal": 1},
            {"nombre": "John Stones",        "pos": "CB",  "edad": 31, "impacto": 81, "dorsal": 5},
            {"nombre": "Marc Guéhi",         "pos": "CB",  "edad": 24, "impacto": 78, "dorsal": 6},
            {"nombre": "Cole Palmer",        "pos": "CAM", "edad": 22, "impacto": 86, "dorsal": 20},
            {"nombre": "Kobbie Mainoo",      "pos": "CM",  "edad": 19, "impacto": 80, "dorsal": 26},
        ],
    },

    "GERMANY": {
        "ranking_fifa": 6, "entrenador": "Julian Nagelsmann",
        "estilo": "pressing intenso, transición rápida",
        "fortaleza": "organización táctica, físico, disciplina",
        "debilidad": "creatividad individual, finalización",
        "jugadores": [
            {"nombre": "Florian Wirtz",      "pos": "CAM", "edad": 21, "impacto": 92, "dorsal": 10},
            {"nombre": "Jamal Musiala",      "pos": "CAM", "edad": 21, "impacto": 91, "dorsal": 14},
            {"nombre": "Kai Havertz",        "pos": "ST",  "edad": 25, "impacto": 84, "dorsal": 7},
            {"nombre": "Joshua Kimmich",     "pos": "CM",  "edad": 29, "impacto": 89, "dorsal": 6},
            {"nombre": "Toni Kroos",         "pos": "CM",  "edad": 34, "impacto": 87, "dorsal": 8},
            {"nombre": "Leroy Sané",         "pos": "LW",  "edad": 28, "impacto": 82, "dorsal": 19},
            {"nombre": "Manuel Neuer",       "pos": "GK",  "edad": 39, "impacto": 85, "dorsal": 1},
            {"nombre": "Antonio Rüdiger",    "pos": "CB",  "edad": 31, "impacto": 84, "dorsal": 2},
            {"nombre": "Robert Andrich",     "pos": "DM",  "edad": 29, "impacto": 79, "dorsal": 23},
            {"nombre": "Deniz Undav",        "pos": "ST",  "edad": 27, "impacto": 78, "dorsal": 14},
            {"nombre": "Jonathan Tah",       "pos": "CB",  "edad": 28, "impacto": 80, "dorsal": 4},
        ],
    },

    "PORTUGAL": {
        "ranking_fifa": 7, "entrenador": "Roberto Martínez",
        "estilo": "juego de posesión + transición con Cristiano",
        "fortaleza": "plantilla equilibrada, experiencia internacional",
        "debilidad": "continuidad post-Ronaldo",
        "jugadores": [
            {"nombre": "Cristiano Ronaldo",  "pos": "ST",  "edad": 41, "impacto": 90, "dorsal": 7},
            {"nombre": "Bruno Fernandes",    "pos": "CAM", "edad": 29, "impacto": 90, "dorsal": 8},
            {"nombre": "Bernardo Silva",     "pos": "CM",  "edad": 29, "impacto": 89, "dorsal": 10},
            {"nombre": "Rafael Leão",        "pos": "LW",  "edad": 25, "impacto": 87, "dorsal": 17},
            {"nombre": "Rúben Dias",         "pos": "CB",  "edad": 27, "impacto": 86, "dorsal": 4},
            {"nombre": "Vitinha",            "pos": "CM",  "edad": 24, "impacto": 83, "dorsal": 13},
            {"nombre": "Diogo Jota",         "pos": "FWD", "edad": 27, "impacto": 82, "dorsal": 11},
            {"nombre": "Rui Patrício",       "pos": "GK",  "edad": 36, "impacto": 79, "dorsal": 1},
            {"nombre": "Nuno Mendes",        "pos": "LB",  "edad": 22, "impacto": 81, "dorsal": 19},
            {"nombre": "João Neves",         "pos": "CM",  "edad": 20, "impacto": 79, "dorsal": 20},
            {"nombre": "Gonçalo Inácio",     "pos": "CB",  "edad": 23, "impacto": 77, "dorsal": 3},
        ],
    },

    "NETHERLANDS": {
        "ranking_fifa": 8, "entrenador": "Ronald Koeman",
        "estilo": "4-3-3 clásico holandés, juego de posesión",
        "fortaleza": "mediocampo creativo, ataque variado",
        "debilidad": "fragilidad defensiva en alta presión",
        "jugadores": [
            {"nombre": "Virgil van Dijk",    "pos": "CB",  "edad": 33, "impacto": 88, "dorsal": 4},
            {"nombre": "Xavi Simons",        "pos": "CAM", "edad": 22, "impacto": 87, "dorsal": 10},
            {"nombre": "Cody Gakpo",         "pos": "LW",  "edad": 25, "impacto": 84, "dorsal": 11},
            {"nombre": "Tijjani Reijnders",  "pos": "CM",  "edad": 26, "impacto": 83, "dorsal": 14},
            {"nombre": "Donyell Malen",      "pos": "RW",  "edad": 25, "impacto": 80, "dorsal": 7},
            {"nombre": "Wout Weghorst",      "pos": "ST",  "edad": 32, "impacto": 75, "dorsal": 9},
            {"nombre": "Bart Verbruggen",    "pos": "GK",  "edad": 22, "impacto": 79, "dorsal": 1},
            {"nombre": "Denzel Dumfries",    "pos": "RB",  "edad": 28, "impacto": 80, "dorsal": 22},
            {"nombre": "Frenkie de Jong",    "pos": "CM",  "edad": 27, "impacto": 85, "dorsal": 21},
            {"nombre": "Ryan Gravenberch",   "pos": "DM",  "edad": 22, "impacto": 82, "dorsal": 5},
            {"nombre": "Joey Veerman",       "pos": "CM",  "edad": 25, "impacto": 76, "dorsal": 17},
        ],
    },

    "UNITED STATES": {
        "ranking_fifa": 11, "entrenador": "Mauricio Pochettino",
        "estilo": "pressing alto, atletismo, organización defensiva",
        "fortaleza": "físico, transición, profundidad en mediocampo",
        "debilidad": "falta de experiencia en grandes torneos",
        "jugadores": [
            {"nombre": "Christian Pulisic",  "pos": "CAM", "edad": 26, "impacto": 88, "dorsal": 10},
            {"nombre": "Weston McKennie",    "pos": "CM",  "edad": 26, "impacto": 80, "dorsal": 8},
            {"nombre": "Gio Reyna",          "pos": "RW",  "edad": 22, "impacto": 83, "dorsal": 7},
            {"nombre": "Tyler Adams",        "pos": "DM",  "edad": 25, "impacto": 80, "dorsal": 4},
            {"nombre": "Ricardo Pepi",       "pos": "ST",  "edad": 22, "impacto": 75, "dorsal": 9},
            {"nombre": "Folarin Balogun",    "pos": "ST",  "edad": 23, "impacto": 74, "dorsal": 9},
            {"nombre": "Matt Turner",        "pos": "GK",  "edad": 30, "impacto": 75, "dorsal": 1},
            {"nombre": "Antonee Robinson",   "pos": "LB",  "edad": 27, "impacto": 78, "dorsal": 5},
            {"nombre": "Yunus Musah",        "pos": "CM",  "edad": 22, "impacto": 79, "dorsal": 6},
            {"nombre": "Sergiño Dest",       "pos": "RB",  "edad": 24, "impacto": 76, "dorsal": 2},
            {"nombre": "Tim Weah",           "pos": "RW",  "edad": 24, "impacto": 75, "dorsal": 11},
        ],
    },

    "MEXICO": {
        "ranking_fifa": 16, "entrenador": "Javier Aguirre",
        "estilo": "contragolpe, presión, disciplina táctica",
        "fortaleza": "apoyo local (sede), experiencia mundialista",
        "debilidad": "limitación ofensiva, desgaste generacional",
        "jugadores": [
            {"nombre": "Hirving Lozano",     "pos": "RW",  "edad": 28, "impacto": 82, "dorsal": 22},
            {"nombre": "Raúl Jiménez",       "pos": "ST",  "edad": 33, "impacto": 79, "dorsal": 9},
            {"nombre": "Guillermo Ochoa",    "pos": "GK",  "edad": 39, "impacto": 82, "dorsal": 13},
            {"nombre": "Edson Álvarez",      "pos": "DM",  "edad": 26, "impacto": 80, "dorsal": 4},
            {"nombre": "Chucky Lozano",      "pos": "RW",  "edad": 29, "impacto": 81, "dorsal": 22},
            {"nombre": "Santiago Giménez",   "pos": "ST",  "edad": 23, "impacto": 80, "dorsal": 14},
            {"nombre": "Jorge Sánchez",      "pos": "RB",  "edad": 23, "impacto": 73, "dorsal": 2},
            {"nombre": "César Montes",       "pos": "CB",  "edad": 26, "impacto": 74, "dorsal": 3},
            {"nombre": "Alexis Vega",        "pos": "LW",  "edad": 27, "impacto": 75, "dorsal": 11},
            {"nombre": "Carlos Rodríguez",   "pos": "CM",  "edad": 27, "impacto": 72, "dorsal": 8},
            {"nombre": "Luis Romo",          "pos": "CM",  "edad": 29, "impacto": 71, "dorsal": 16},
        ],
    },

    "URUGUAY": {
        "ranking_fifa": 12, "entrenador": "Marcelo Bielsa",
        "estilo": "intensidad extrema, pressing, disciplina táctica Bielsa",
        "fortaleza": "experiencia, dureza defensiva",
        "debilidad": "edad de figuras clave",
        "jugadores": [
            {"nombre": "Federico Valverde",  "pos": "CM",  "edad": 25, "impacto": 93, "dorsal": 14},
            {"nombre": "Darwin Núñez",       "pos": "ST",  "edad": 25, "impacto": 88, "dorsal": 9},
            {"nombre": "Luis Suárez",        "pos": "ST",  "edad": 37, "impacto": 80, "dorsal": 9},
            {"nombre": "Rodrigo Bentancur",  "pos": "CM",  "edad": 27, "impacto": 82, "dorsal": 30},
            {"nombre": "Ronald Araújo",      "pos": "CB",  "edad": 25, "impacto": 85, "dorsal": 2},
            {"nombre": "Sergio Rochet",      "pos": "GK",  "edad": 29, "impacto": 78, "dorsal": 1},
            {"nombre": "Maximiliano Araújo", "pos": "LW",  "edad": 23, "impacto": 76, "dorsal": 19},
            {"nombre": "Facundo Pellistri",  "pos": "RW",  "edad": 22, "impacto": 75, "dorsal": 11},
            {"nombre": "José María Giménez","pos": "CB",  "edad": 29, "impacto": 80, "dorsal": 3},
            {"nombre": "Nahitan Nández",     "pos": "RB",  "edad": 28, "impacto": 74, "dorsal": 15},
            {"nombre": "Nicolás de la Cruz", "pos": "CAM", "edad": 27, "impacto": 79, "dorsal": 10},
        ],
    },

    "COLOMBIA": {
        "ranking_fifa": 9, "entrenador": "Néstor Lorenzo",
        "estilo": "fútbol ofensivo, velocidad en bandas",
        "fortaleza": "ataque con Díaz y Vidal, creatividad",
        "debilidad": "inconsistencia defensiva",
        "jugadores": [
            {"nombre": "James Rodríguez",    "pos": "CAM", "edad": 33, "impacto": 87, "dorsal": 10},
            {"nombre": "Luis Díaz",          "pos": "LW",  "edad": 27, "impacto": 90, "dorsal": 7},
            {"nombre": "Jhon Córdoba",       "pos": "ST",  "edad": 30, "impacto": 77, "dorsal": 9},
            {"nombre": "Wilmar Barrios",     "pos": "DM",  "edad": 31, "impacto": 76, "dorsal": 5},
            {"nombre": "Davinson Sánchez",   "pos": "CB",  "edad": 27, "impacto": 80, "dorsal": 2},
            {"nombre": "Matheus Uribe",      "pos": "CM",  "edad": 33, "impacto": 74, "dorsal": 13},
            {"nombre": "Cuadrado",           "pos": "RB",  "edad": 36, "impacto": 77, "dorsal": 11},
            {"nombre": "Camilo Vargas",      "pos": "GK",  "edad": 32, "impacto": 74, "dorsal": 12},
            {"nombre": "Richard Ríos",       "pos": "CM",  "edad": 24, "impacto": 78, "dorsal": 20},
            {"nombre": "Jhon Jáder Durán",   "pos": "ST",  "edad": 20, "impacto": 76, "dorsal": 21},
            {"nombre": "Jorge Carrascal",    "pos": "CM",  "edad": 24, "impacto": 74, "dorsal": 18},
        ],
    },

    "MOROCCO": {
        "ranking_fifa": 13, "entrenador": "Walid Regragui",
        "estilo": "bloque defensivo compacto, transición veloz",
        "fortaleza": "unidad colectiva, mentalidad ganadora",
        "debilidad": "creatividad ofensiva limitada sin Ziyech",
        "jugadores": [
            {"nombre": "Hakim Ziyech",       "pos": "CAM", "edad": 31, "impacto": 85, "dorsal": 7},
            {"nombre": "Achraf Hakimi",      "pos": "RB",  "edad": 25, "impacto": 90, "dorsal": 2},
            {"nombre": "Sofiane Boufal",     "pos": "LW",  "edad": 30, "impacto": 78, "dorsal": 11},
            {"nombre": "Noussair Mazraoui",  "pos": "RB",  "edad": 26, "impacto": 82, "dorsal": 22},
            {"nombre": "Romain Saïss",       "pos": "CB",  "edad": 34, "impacto": 77, "dorsal": 5},
            {"nombre": "Sofyan Amrabat",     "pos": "DM",  "edad": 27, "impacto": 84, "dorsal": 4},
            {"nombre": "Yassine Bounou",     "pos": "GK",  "edad": 32, "impacto": 83, "dorsal": 1},
            {"nombre": "Youssef En-Nesyri",  "pos": "ST",  "edad": 27, "impacto": 79, "dorsal": 19},
            {"nombre": "Azzedine Ounahi",    "pos": "CM",  "edad": 23, "impacto": 78, "dorsal": 8},
            {"nombre": "Ilias Chair",        "pos": "CM",  "edad": 26, "impacto": 74, "dorsal": 14},
            {"nombre": "Adam Aznou",         "pos": "LB",  "edad": 19, "impacto": 70, "dorsal": 3},
        ],
    },

    "SENEGAL": {
        "ranking_fifa": 18, "entrenador": "Aliou Cissé",
        "estilo": "físico, directo, presión media-alta",
        "fortaleza": "fisicidad, velocidad, Mané al frente",
        "debilidad": "creación de juego, finalización",
        "jugadores": [
            {"nombre": "Sadio Mané",         "pos": "LW",  "edad": 32, "impacto": 90, "dorsal": 10},
            {"nombre": "Édouard Mendy",      "pos": "GK",  "edad": 32, "impacto": 83, "dorsal": 16},
            {"nombre": "Kalidou Koulibaly",  "pos": "CB",  "edad": 33, "impacto": 82, "dorsal": 3},
            {"nombre": "Ismaïla Sarr",       "pos": "RW",  "edad": 26, "impacto": 82, "dorsal": 23},
            {"nombre": "Idrissa Gueye",      "pos": "DM",  "edad": 34, "impacto": 79, "dorsal": 5},
            {"nombre": "Cheikhou Kouyaté",   "pos": "CM",  "edad": 34, "impacto": 74, "dorsal": 8},
            {"nombre": "Nicolas Jackson",    "pos": "ST",  "edad": 23, "impacto": 80, "dorsal": 9},
            {"nombre": "Pape Matar Sarr",    "pos": "CM",  "edad": 22, "impacto": 78, "dorsal": 18},
            {"nombre": "Abdou Diallo",       "pos": "CB",  "edad": 27, "impacto": 75, "dorsal": 4},
            {"nombre": "Lamine Camara",      "pos": "CM",  "edad": 21, "impacto": 76, "dorsal": 6},
            {"nombre": "Boulaye Dia",        "pos": "ST",  "edad": 27, "impacto": 79, "dorsal": 11},
        ],
    },

    "JAPAN": {
        "ranking_fifa": 17, "entrenador": "Hajime Moriyasu",
        "estilo": "pressing ultra intenso, juego colectivo, disciplina táctica",
        "fortaleza": "unidad, pressing, eficiencia ofensiva",
        "debilidad": "estatura en defensas, experiencia en etapas avanzadas",
        "jugadores": [
            {"nombre": "Takumi Minamino",    "pos": "CAM", "edad": 29, "impacto": 82, "dorsal": 10},
            {"nombre": "Ritsu Doan",         "pos": "RW",  "edad": 26, "impacto": 84, "dorsal": 9},
            {"nombre": "Junya Ito",          "pos": "RW",  "edad": 31, "impacto": 80, "dorsal": 7},
            {"nombre": "Ao Tanaka",          "pos": "CM",  "edad": 25, "impacto": 79, "dorsal": 6},
            {"nombre": "Wataru Endo",        "pos": "DM",  "edad": 31, "impacto": 78, "dorsal": 8},
            {"nombre": "Takehiro Tomiyasu",  "pos": "CB",  "edad": 25, "impacto": 78, "dorsal": 5},
            {"nombre": "Shuichi Gonda",      "pos": "GK",  "edad": 33, "impacto": 75, "dorsal": 23},
            {"nombre": "Daichi Kamada",      "pos": "CAM", "edad": 28, "impacto": 80, "dorsal": 7},
            {"nombre": "Takefusa Kubo",      "pos": "RW",  "edad": 23, "impacto": 82, "dorsal": 17},
            {"nombre": "Maya Yoshida",       "pos": "CB",  "edad": 36, "impacto": 74, "dorsal": 22},
            {"nombre": "Kaoru Mitoma",       "pos": "LW",  "edad": 26, "impacto": 83, "dorsal": 11},
        ],
    },

    "SOUTH KOREA": {
        "ranking_fifa": 23, "entrenador": "Hong Myung-bo",
        "estilo": "pressing, físico, ataque por Son",
        "fortaleza": "Son en ofensiva, cohesión de equipo",
        "debilidad": "dependencia extrema de Son",
        "jugadores": [
            {"nombre": "Son Heung-min",      "pos": "LW",  "edad": 32, "impacto": 93, "dorsal": 7},
            {"nombre": "Lee Kang-in",        "pos": "CAM", "edad": 23, "impacto": 84, "dorsal": 10},
            {"nombre": "Hwang Hee-chan",     "pos": "ST",  "edad": 28, "impacto": 79, "dorsal": 11},
            {"nombre": "Kim Min-jae",        "pos": "CB",  "edad": 27, "impacto": 85, "dorsal": 3},
            {"nombre": "Jung Woo-young",     "pos": "DM",  "edad": 34, "impacto": 73, "dorsal": 16},
            {"nombre": "Hwang In-beom",      "pos": "CM",  "edad": 27, "impacto": 76, "dorsal": 5},
            {"nombre": "Cho Gue-sung",       "pos": "ST",  "edad": 25, "impacto": 75, "dorsal": 9},
            {"nombre": "Kim Seung-gyu",      "pos": "GK",  "edad": 33, "impacto": 73, "dorsal": 21},
            {"nombre": "Na Sang-ho",         "pos": "LW",  "edad": 27, "impacto": 74, "dorsal": 17},
            {"nombre": "Kim Jin-su",         "pos": "LB",  "edad": 31, "impacto": 72, "dorsal": 12},
            {"nombre": "Lee Jae-sung",       "pos": "CM",  "edad": 31, "impacto": 74, "dorsal": 14},
        ],
    },

    "ITALY": {
        "ranking_fifa": 10, "entrenador": "Luciano Spalletti",
        "estilo": "juego posicional, pressing organizado",
        "fortaleza": "mediocampo técnico, solidez defensiva",
        "debilidad": "ataque sin figuras de elite",
        "jugadores": [
            {"nombre": "Federico Chiesa",    "pos": "RW",  "edad": 26, "impacto": 83, "dorsal": 14},
            {"nombre": "Sandro Tonali",      "pos": "CM",  "edad": 24, "impacto": 83, "dorsal": 8},
            {"nombre": "Ciro Immobile",      "pos": "ST",  "edad": 34, "impacto": 78, "dorsal": 17},
            {"nombre": "Gianluigi Donnarumma","pos":"GK",  "edad": 25, "impacto": 86, "dorsal": 1},
            {"nombre": "Alessandro Bastoni", "pos": "CB",  "edad": 25, "impacto": 84, "dorsal": 23},
            {"nombre": "Nicolò Barella",     "pos": "CM",  "edad": 27, "impacto": 87, "dorsal": 18},
            {"nombre": "Lorenzo Pellegrini", "pos": "CAM", "edad": 27, "impacto": 80, "dorsal": 10},
            {"nombre": "Giacomo Raspadori",  "pos": "ST",  "edad": 24, "impacto": 78, "dorsal": 18},
            {"nombre": "Davide Frattesi",    "pos": "CM",  "edad": 25, "impacto": 79, "dorsal": 10},
            {"nombre": "Giovanni Di Lorenzo","pos": "RB",  "edad": 30, "impacto": 79, "dorsal": 2},
            {"nombre": "Federico Dimarco",   "pos": "LB",  "edad": 26, "impacto": 80, "dorsal": 3},
        ],
    },

    "AUSTRALIA": {
        "ranking_fifa": 24, "entrenador": "Tony Popovic",
        "estilo": "bloque bajo, contraataque, físico",
        "fortaleza": "Leckie, experiencia Socceroos",
        "debilidad": "ataque sin potencia, dependencia de Leckie",
        "jugadores": [
            {"nombre": "Mathew Leckie",      "pos": "RW",  "edad": 33, "impacto": 80, "dorsal": 7},
            {"nombre": "Mitchell Duke",      "pos": "ST",  "edad": 33, "impacto": 73, "dorsal": 20},
            {"nombre": "Mat Ryan",           "pos": "GK",  "edad": 32, "impacto": 76, "dorsal": 1},
            {"nombre": "Harry Souttar",      "pos": "CB",  "edad": 25, "impacto": 77, "dorsal": 6},
            {"nombre": "Ajdin Hrustic",      "pos": "CM",  "edad": 28, "impacto": 74, "dorsal": 11},
            {"nombre": "Aaron Mooy",         "pos": "CM",  "edad": 33, "impacto": 78, "dorsal": 13},
            {"nombre": "Aziz Behich",        "pos": "LB",  "edad": 33, "impacto": 72, "dorsal": 5},
            {"nombre": "Jackson Irvine",     "pos": "CM",  "edad": 31, "impacto": 73, "dorsal": 8},
            {"nombre": "Garang Kuol",        "pos": "ST",  "edad": 20, "impacto": 71, "dorsal": 15},
            {"nombre": "Riley McGree",       "pos": "CM",  "edad": 25, "impacto": 74, "dorsal": 14},
            {"nombre": "Cameron Devlin",     "pos": "CM",  "edad": 25, "impacto": 70, "dorsal": 17},
        ],
    },

    "CANADA": {
        "ranking_fifa": 41, "entrenador": "Jesse Marsch",
        "estilo": "pressing, físico, verticalidad",
        "fortaleza": "Davies en banda, generación joven",
        "debilidad": "experiencia en torneos mayores",
        "jugadores": [
            {"nombre": "Alphonso Davies",    "pos": "LB",  "edad": 23, "impacto": 93, "dorsal": 19},
            {"nombre": "Jonathan David",     "pos": "ST",  "edad": 24, "impacto": 87, "dorsal": 20},
            {"nombre": "Tajon Buchanan",     "pos": "RW",  "edad": 25, "impacto": 80, "dorsal": 11},
            {"nombre": "Milan Borjan",       "pos": "GK",  "edad": 36, "impacto": 74, "dorsal": 18},
            {"nombre": "Atiba Hutchinson",   "pos": "CM",  "edad": 41, "impacto": 68, "dorsal": 13},
            {"nombre": "Stephen Eustaquio",  "pos": "DM",  "edad": 27, "impacto": 77, "dorsal": 7},
            {"nombre": "Cyle Larin",         "pos": "ST",  "edad": 29, "impacto": 74, "dorsal": 17},
            {"nombre": "Sam Adekugbe",       "pos": "LB",  "edad": 28, "impacto": 72, "dorsal": 3},
            {"nombre": "Richie Laryea",      "pos": "RB",  "edad": 29, "impacto": 71, "dorsal": 22},
            {"nombre": "Liam Millar",        "pos": "RW",  "edad": 24, "impacto": 72, "dorsal": 9},
            {"nombre": "Ismaël Koné",        "pos": "CM",  "edad": 22, "impacto": 74, "dorsal": 8},
        ],
    },

    "BELGIUM": {
        "ranking_fifa": 14, "entrenador": "Domenico Tedesco",
        "estilo": "juego directo, transición, individualidades",
        "fortaleza": "jugadores de elite en Premier League",
        "debilidad": "final de generación dorada",
        "jugadores": [
            {"nombre": "Kevin De Bruyne",    "pos": "CAM", "edad": 33, "impacto": 95, "dorsal": 7},
            {"nombre": "Romelu Lukaku",      "pos": "ST",  "edad": 31, "impacto": 84, "dorsal": 9},
            {"nombre": "Axel Witsel",        "pos": "DM",  "edad": 35, "impacto": 73, "dorsal": 6},
            {"nombre": "Youri Tielemans",    "pos": "CM",  "edad": 27, "impacto": 80, "dorsal": 8},
            {"nombre": "Leandro Trossard",   "pos": "LW",  "edad": 29, "impacto": 81, "dorsal": 11},
            {"nombre": "Jeremy Doku",        "pos": "RW",  "edad": 22, "impacto": 83, "dorsal": 10},
            {"nombre": "Wout Faes",          "pos": "CB",  "edad": 26, "impacto": 76, "dorsal": 5},
            {"nombre": "Koen Casteels",      "pos": "GK",  "edad": 32, "impacto": 77, "dorsal": 1},
            {"nombre": "Amadou Onana",       "pos": "CM",  "edad": 22, "impacto": 79, "dorsal": 14},
            {"nombre": "Arthur Theate",      "pos": "CB",  "edad": 24, "impacto": 76, "dorsal": 3},
            {"nombre": "Charles De Ketelaere","pos":"CAM", "edad": 23, "impacto": 78, "dorsal": 17},
        ],
    },
}

# ── Aliases para nombres alternativos de ESPN ──────────────────────────────────
ALIASES: dict[str, str] = {
    "USA": "UNITED STATES",
    "ESTADOS UNIDOS": "UNITED STATES",
    "UNITED STATES OF AMERICA": "UNITED STATES",
    "BRASIL": "BRAZIL",
    "ALEMANIA": "GERMANY",
    "PAÍSES BAJOS": "NETHERLANDS",
    "HOLANDA": "NETHERLANDS",
    "COREA DEL SUR": "SOUTH KOREA",
    "COREA": "SOUTH KOREA",
    "MARRUECOS": "MOROCCO",
    "SENEGAL": "SENEGAL",
    "ITALIA": "ITALY",
    "BÉLGICA": "BELGIUM",
    "COLOMBIA": "COLOMBIA",
    "JAPÓN": "JAPAN",
    "AUSTRALIA": "AUSTRALIA",
    "CANADÁ": "CANADA",
    "FRANCIA": "FRANCE",
    "ESPAÑA": "SPAIN",
    "INGLATERRA": "ENGLAND",
    "PORTUGAL": "PORTUGAL",
    "ARGENTINA": "ARGENTINA",
    "URUGUAY": "URUGUAY",
}


def get_squad(team_name: str) -> dict | None:
    """
    Busca el equipo por nombre (flexible: mayúsculas, aliases).
    Retorna el dict del equipo o None si no se encuentra.
    """
    upper = team_name.upper().strip()
    # Búsqueda directa
    if upper in SQUADS:
        return SQUADS[upper]
    # Alias
    resolved = ALIASES.get(upper)
    if resolved and resolved in SQUADS:
        return SQUADS[resolved]
    # Búsqueda parcial
    for key in SQUADS:
        if key in upper or upper in key or upper.split()[0] in key:
            return SQUADS[key]
    return None
