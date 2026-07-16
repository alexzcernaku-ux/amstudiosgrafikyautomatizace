# AM Studios — Automatizace grafiky ze Slacku

## Jak to bude fungovat

```
#grafika kanál (Slack)
  → "Potřebuju grafiku na [téma]" + foto (volitelně)
     → Claude (Anthropic API) rozpozná pilíř a co chybí
        → chybí něco? → doptá se ve vlákně, čeká na odpověď
        → má vše? → vybere šablonu, vyplní daty, vyrenderuje
           → pošle hotové PNG + navržené texty/CTA zpátky do vlákna
```

Stav rozhovoru (co se ví/chybí) se drží ve Supabase — stejný projekt, co už máš pro leady, jen nová tabulka. Díky tomu funguje i vícekrokové doptávání přes samostatné, krátké Slack eventy.

## Pilíře a jejich povinná pole

| Pilíř | Potřebná pole | Kdo je dodává |
|---|---|---|
| Edukativní | jen téma | nikdo — Claude vymyslí sám |
| Z nemovitosti | foto, dispozice, lokalita, makléř (+agentura) | Alex/tým, vždy se ptát na chybějící |
| BTS | syrové fotky z natáčení | Alex/tým |
| Vtipné | jen nálada/téma (volitelné) | nikdo — volná ruka |
| Mýty/srovnání | tvrzení + realita | Alex/tým |
| YT náhled / Shorts | foto, dispozice, lokalita, makléř | Alex/tým (stejná data jako Z nemovitosti) |

## Technický stack

- **Backend:** Python (Flask) + Slack Bolt SDK — stejný jazyk jako renderovací pipeline, žádné překvápka při portování šablon
- **Renderování:** WeasyPrint (přesně to, co jsme celou dobu testovali a ověřovali tady)
- **Hosting:** Railway (Docker, žádné umělé časové limity jako u Netlify)
- **Stav rozhovoru:** Supabase (nová tabulka `grafika_requests`)
- **AI vrstva:** Anthropic API (Claude) — klasifikace pilíře, extrakce polí, generování doptávek i textů

## Pořadí buildu (i když jedeme na celý záběr, kód se nepíše najednou)

1. Kostra: Slack event receiver + uložení do Supabase
2. AI routing: rozpoznání pilíře + chybějících polí
3. Šablony: portování všech existujících HTML vzorů do knihovny
4. Renderování + odeslání zpět do Slacku
5. Testování na reálných požadavcích, doladění promptů
