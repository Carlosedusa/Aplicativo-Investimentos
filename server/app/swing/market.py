"""B3: horário de Brasília, feriados e janela de entradas (swing trade com ações)."""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

SP = ZoneInfo("America/Sao_Paulo")
OPEN, CLOSE = time(10, 0), time(17, 55)
NO_ENTRIES_BEFORE, NO_ENTRIES_AFTER = time(10, 15), time(17, 0)
HOLIDAYS = {
    "2026-01-01": "Confraternização Universal", "2026-02-16": "Carnaval", "2026-02-17": "Carnaval",
    "2026-04-03": "Sexta-feira Santa", "2026-04-21": "Tiradentes", "2026-05-01": "Dia do Trabalho",
    "2026-06-04": "Corpus Christi", "2026-09-07": "Independência", "2026-10-12": "Nossa Sra. Aparecida",
    "2026-11-02": "Finados", "2026-11-20": "Consciência Negra", "2026-12-24": "Véspera de Natal",
    "2026-12-25": "Natal", "2026-12-31": "Véspera de Ano Novo",
}


def entry_window(now: datetime) -> list[str]:
    """Motivos pelos quais não se pode abrir posição agora (vazio = liberado)."""
    local = now.astimezone(SP)
    d: date = local.date()
    stamp = local.strftime("%d/%m %H:%M")
    if d.weekday() >= 5:
        return ["Bolsa fechada hoje (fim de semana, %s em Brasília)." % stamp]
    if d.isoformat() in HOLIDAYS:
        return ["Bolsa fechada hoje (feriado: %s)." % HOLIDAYS[d.isoformat()]]
    t = local.time().replace(second=0, microsecond=0)
    if t < OPEN or t >= CLOSE:
        return ["Bolsa fechada agora (%s em Brasília). Pregão das %s às %s." % (stamp, OPEN.strftime("%H:%M"), CLOSE.strftime("%H:%M"))]
    if t < NO_ENTRIES_BEFORE:
        return ["Sem entradas antes das %s (abertura volátil)." % NO_ENTRIES_BEFORE.strftime("%H:%M")]
    if t > NO_ENTRIES_AFTER:
        return ["Sem novas entradas depois das %s (leilão de fechamento)." % NO_ENTRIES_AFTER.strftime("%H:%M")]
    return []
