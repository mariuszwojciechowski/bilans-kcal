"""Kształt maila resetu hasła — plain tekst bez wysyłki (`_send` zamockowany)."""
from app.services import mail


def test_reset_mail_shape(monkeypatch):
    sent = {}

    def fake_send(to, subject, text):
        sent.update(to=to, subject=subject, text=text)
        return True

    monkeypatch.setattr(mail, "_send", fake_send)
    assert mail.send_password_reset("a@b.pl", "https://fit.krasnal.cc/password-reset/TKN")
    assert sent["to"] == "a@b.pl"
    assert "reset hasła" in sent["subject"]
    text = sent["text"]
    assert "https://fit.krasnal.cc/password-reset/TKN" in text
    assert "nowe hasło" in text  # regresja: było „nowy hasło"
    assert text.endswith("Serdecznie pozdrawiam,\n\n\tFit Krasnal\n")
    assert mail._KRASNAL in text
    assert any(f'"{quote}"' in text for quote in mail._KRASNAL_WISDOM)


def test_reset_mail_wisdom_stays_polite():
    """Cytaty do maila (w przeciwieństwie do quips.json) mają być grzeczne —
    test pilnuje, żeby nikt nie podmienił listy na teksty z panelu „Dodaj"."""
    for quote in mail._KRASNAL_WISDOM:
        low = quote.lower()
        for rude in ("kurwa", "choler", "pierdol", "skurwy", "diaska",
                     "jezusa maria", "gówno", "dupa", "jasna ciasna"):
            assert rude not in low, f"cytat do maila przestał być grzeczny: {quote!r}"
