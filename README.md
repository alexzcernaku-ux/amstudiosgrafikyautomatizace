# AM Studios — Grafika ze Slacku (automatizace)

**Stav: funkční, otestované.** Všech 6 pilířů jsem prohnal reálným renderováním
(ne jen kontrolou syntaxe) — šablony vyrenderují správně, bez překryvů, žádné
další úpravy HTML nejsou potřeba. Jediné, co jsem odsud nemohl otestovat, je
samotné SKUTEČNÉ volání Slack a Anthropic API (nemám tvoje klíče) — to prosím
ověř podle kroku 4 níže hned po nasazení.

## Co dělá a jak

```
#grafika kanál (Slack)
  → "Potřebuju grafiku na [téma]" + foto (volitelně)
     → Claude rozpozná pilíř a co chybí
        → chybí něco? → doptá se ve vlákně, čeká na odpověď
        → má vše? → vygeneruje/vyplní obsah, vyrenderuje, pošle PNG zpět
```

**6 pilířů:**
- **Z nemovitosti** — pevná šablona, 6 slidů, data od tebe (foto, dispozice, lokalita, makléř, popis, služby)
- **YT náhled / Shorts** — stejná data, 16:9 a/nebo 9:16
- **BTS** — počet slidů = počet fotek, co pošleš
- **Edukativní** — jen téma, Claude napíše celý obsah **a sám rozhodne, kolik slidů** (jednoduché téma ~5-6, širší téma až 8-10)
- **Mýty/srovnání** — jen tvrzení k vyvrácení, stejná proměnlivá délka
- **Vtipné** — volná ruka, žádná pevná šablona, Claude navrhne úplně nové HTML podle 2 schválených vzorů

Edukativní a Mýty se skládají z knihovny opakovaně použitelných bloků
(`templates/slides/*.html`) — Claude si sám vybere, kolik bloků a jakých použije.

## Co už máš hotové

Slack bota máš založeného — super, to je krok 2 z původního plánu hotový.
Zbývá:

## 1. Zkontroluj Slack App nastavení

Ověř, že máš:
- **OAuth & Permissions** → Bot Token Scopes: `chat:write`, `files:write`, `channels:history`, `channels:read`
- **Event Subscriptions** → zapnuté, Subscribe to bot events → `message.channels`
- Bota pozvaného do #grafika (`/invite @jméno-bota`)
- Zkopírovaný **Bot User OAuth Token** (`xoxb-...`) a **Signing Secret** (Basic Information)
- Channel ID kanálu #grafika (klikni na název kanálu → dole)

Request URL v Event Subscriptions doplníš až po kroku 3 (Railway ti dá adresu).

## 2. Založ Supabase tabulku

SQL Editor → spusť:

```sql
create table if not exists grafika_requests (
  id uuid primary key default gen_random_uuid(),
  thread_ts text not null unique,
  channel_id text not null,
  pillar text,
  collected_data jsonb not null default '{}',
  status text not null default 'sbírání_dat',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
```

Potřebuješ **service_role key** (Project Settings → API → `service_role` `secret`) —
ne anon key, tohle běží na serveru.

## 3. Nasaď na Railway

1. Nahraj tuhle složku do vlastního GitHub repa (jako u landing page)
2. railway.app → **New Project** → **Deploy from GitHub repo** — Railway sám pozná Dockerfile
3. **Variables** → přidej:
   - `SLACK_BOT_TOKEN`
   - `SLACK_SIGNING_SECRET`
   - `ANTHROPIC_API_KEY` (console.anthropic.com → API Keys)
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_KEY`
   - `GRAFIKA_CHANNEL_ID`
4. **Settings** → **Networking** → **Generate Domain**
5. Vrať se do Slack App → Event Subscriptions → Request URL: `https://tvuj-projekt.up.railway.app/slack/events`

## 4. Otestuj

Napiš do #grafika: `Potřebuju edukativní carousel na téma proč se vyplatí drone foto` (bez fotky)

Očekávané chování: bot napíše "Dík, mám vše — dělám grafiku..." a během cca 10-20
vteřin (několik AI volání + renderování víc slidů) pošle hotové PNG do vlákna.

Zkus i něco s fotkou: `Potřebuju grafiku na Plzeň, 2+kk, makléřka Jana Mudrová z 3K Holding` + přiložená fotka.

Pokud něco nesedí, pošli mi screenshot chybové hlášky (Railway → Deployments → Logs
ukáže přesně, kde to spadlo) — doladíme to spolu.

## Poznámka k nákladům

Každý požadavek dělá 1-2 volání Anthropic API (routing + případně generování obsahu).
Delší edukativní/mýty carousely (8-10 slidů) stojí o něco víc než krátké — Claude
generuje víc textu najednou. Řádově jde o haléře až jednotky korun na požadavek,
ne částky, co by měly zásadně ovlivnit rozpočet.
