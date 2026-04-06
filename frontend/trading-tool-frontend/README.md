# 🧠 Trading Tool Frontend (Next.js + Tailwind)

Een moderne webapp die real-time Bitcoin-marktgegevens, technische analyse en macro-economische indicatoren toont – gebouwd met Next.js, Tailwind CSS en component-based design.

## 📦 Features
- ✅ Live Bitcoin en Solana marketdata (prijs, volume, RSI, 200MA)
- ✅ Grafieken en visuele meters (ScoreGauges voor Macro, Technisch, Setup)
- ✅ Technische en macro-indicatoren per asset
- ✅ Setup-editor met AI-uitleg en strategieën
- 🧠 Integratie met backend-API's voor automatische rapportage en signalen

---

## 🚀 Installatie

### 🔧 Vereisten
- Node.js + pnpm (of npm)
- Git

### 📥 Clonen en draaien
```bash
git clone https://github.com/gvangalen/trading-tool-frontend.git
cd trading-tool-frontend
pnpm install   # of: npm install
pnpm dev       # of: npm run dev

### 🌍 Live deploy (aanbevolen)
1. Ga naar [vercel.com](https://vercel.com)
2. Verbind deze GitHub-repo
3. Klaar – je frontend draait online!

---

## 📡 API-bronnen
- CoinGecko API (voor BTC/SOL data)
- Eigen backend-API’s (bijv. `/api/market`, `/api/macro`, `/api/technical`, `/api/setup`, `/api/strategie`)

---

## 🔭 Roadmap
- ✅ Next.js + Tailwind basis
- ✅ Dashboardpagina met score-gauges en marktdata
- ⏳ Setup-formulieren en strategie-editor integreren
- ⏳ Realtime API-koppelingen toevoegen
- ⏳ AI-module voor automatische strategie-uitleg
- ⏳ Gebruikersauthenticatie + favorieten

---

## 💡 Contributie
Wil je meewerken of feedback geven? Open gerust een issue of stuur een PR. Voor grotere wijzigingen: overleg eerst even.

---

## 🧠 Team & Tools
- Gebouwd door [gvangalen](https://github.com/gvangalen)
- Stack: Next.js, Tailwind, shadcn/ui, Chart.js, CoinGecko, PostgreSQL, AI via OpenAI

## 🔄 Test: frontend deploy via GitHub Actions (22 mei)
