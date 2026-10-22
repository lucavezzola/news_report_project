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
