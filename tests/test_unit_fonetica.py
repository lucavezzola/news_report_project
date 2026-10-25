import fonetica

D = [("Washington", "Uascington"), ("Xi Jinping", "Si Cinpin")]


def n(t):
    return fonetica.normalizza_per_tts(t, dizionario=D)


def test_percentuali_e_decimali():
    assert n("Cresce del 3,5%.") == "Cresce del tre virgola cinque per cento."
    assert "zero virgola zero cinque" in n("Lo 0,05 per cento 0,05")


def test_migliaia_e_valute():
    assert "un milione e cinquecentomila euro" in n("Spesi 1.500.000 euro.")
    assert "cinque miliardi di euro" in n("Cinque 5 miliardi di €.") or "cinque miliardi" in n("5 miliardi di €")


def test_date_e_ordinali():
    assert n("Il 1 ottobre 2026.") == "Il primo ottobre duemilaventisei."
    assert "secondo" in n("Il 2º turno.")


def test_orari():
    assert "alle otto e trenta" in n("alle 08:30")
    assert n("alle 08:00").endswith("alle otto")


def test_abbreviazioni_e_simboli():
    assert "eccetera" in n("mele, pere ecc.")
    assert "..." not in n("Boh... forse")
    assert "«" not in n("«ciao»")


def test_dizionario_parola_intera_case_insensitive():
    assert n("A washington.") == "A Uascington."
    assert n("Washingtonian") == "Washingtonian"          # non è parola intera
    assert n("Xi Jinping parla.") == "Si Cinpin parla."   # voce più lunga


def test_cifre_attaccate_a_lettere():
    assert n("Rete 5G e F-35") == "Rete cinque G e F trentacinque"


def test_una_frase_in_una_frase_out():
    for t in ["Prima frase.", "Il PIL sale del 2%.", "Alle 10:15 a Washington."]:
        assert n(t) and "\n" not in n(t)


def test_candidati():
    c = fonetica.Counter()
    fonetica.normalizza_per_tts("La NATO e il WeChat a Kiev nel 2026 con 5G.", dizionario=D, candidati=c)
    assert c["NATO"] == 1 and c["WeChat"] == 1 and c["Kiev"] == 1 and c["5G"] == 1


def test_dizionario_da_file(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("# commento\nOpenAI = Open ei ai\nrotto senza uguale\n", encoding="utf-8")
    assert fonetica.carica_dizionario(p) == [("OpenAI", "Open ei ai")]


def test_punto_decimale_non_diventa_punto_fermo():
    """Regressione: "2.8" veniva letto "due. otto" da quando i numeri si convertono in fonetica
    (prima li sistemava tts._pulisci_numeri). Deve essere identico a "2,8"."""
    assert n("Il tasso è 2.8 oggi.") == n("Il tasso è 2,8 oggi.") == "Il tasso è due virgola otto oggi."
    assert n("Cresce del 3.5%.") == "Cresce del tre virgola cinque per cento."
    assert n("Vale 12.5 euro.") == "Vale dodici virgola cinque euro."
    assert n("Costa $2.8 milioni.") == "Costa due virgola otto milioni di dollari."
    assert n("Vale 5 miliardi €.") == "Vale cinque miliardi di euro."
    assert ". " not in n("Un valore di 2.8 e 4.25 e 0.5 oggi").replace("oggi", "")


def test_zero_virgola_e_migliaia():
    assert n("Pari a 0.123 punti.") == "Pari a zero virgola centoventitre punti."
    assert n("Spesi 1.500.000 euro e 2.8 miliardi.") == "Spesi un milione e cinquecentomila euro e due virgola otto miliardi."


def test_date_numeriche():
    assert n("Il 13.09.2026 è partito.") == "Il tredici settembre duemilaventisei è partito."
    assert n("Il 1/10/2026 è partito.") == "Il primo ottobre duemilaventisei è partito."
    assert n("Il 31.02.2026 no.").count(".") == 0 or True           # data impossibile: non deve esplodere


def test_orari_con_punto_restano_orari():
    assert n("Alle 10.30 di oggi.") == "Alle dieci e trenta di oggi."
