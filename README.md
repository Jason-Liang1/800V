# NVIDIA 800 VDC 動態估值監控網站 v2

本套件把原本的 NVIDIA 800 VDC 架構／供應鏈網站，新增為「最新完成收盤價 vs. 中期理想情境價」的動態監控頁。

## 快速查看

- `standalone_snapshot.html`：單檔離線版，內建建置時的價格快照；直接用瀏覽器開啟即可。
- `index.html`：部署版入口，會讀取 `data/market_prices.js` 與 `data/valuation_targets.js`。

離線檔不會自行改寫本機價格。真正的每日更新需部署至 GitHub Pages，或在本機執行更新器。

## 部署至 GitHub Pages並每天更新收盤價

1. 將本資料夾**全部檔案（包含隱藏的 `.github` 資料夾）**放進新的 GitHub repository，預設分支為 `main`。
2. 到 Repository → **Settings → Pages**。
3. 在 **Build and deployment → Source** 選擇 **GitHub Actions**。
4. 到 **Actions**，手動執行一次 `Update closing prices and deploy site`。
5. 工作流之後於週一至週五 **22:45 UTC（台北時間翌日 06:45）**執行：
   - 抓取最近完成的台股與美股日收盤價；
   - 更新 `data/market_prices.js` 與 `data/market_prices.json`；
   - 將價格快照 commit 回 repository；
   - 重新部署 GitHub Pages。

排程可能受 GitHub Actions 佇列影響而延後，因此網站會顯示「價格日、產生時間、失敗數與過期狀態」，不假設每次都準點完成。

## 行情更新邏輯

- 僅使用**完成交易日的日收盤價**，不把盤中價格誤當收盤。
- 台股代號使用 `.TW`／`.TWO`；ABB 在網站顯示 `ABB`，行情代號使用美國 ADR `ABBNY`。
- 每個代號最多重試三次。
- 單一代號抓取失敗時，保留上次成功值並標記 `stale`，不會把整張表清空。
- 行情透過 `yfinance` 取得 Yahoo Finance 公開資料，不需要 API Key；此方案適合個人研究與低頻監控，不是交易所級行情服務。

## 理想情境價的定義

- 位於 `data/valuation_targets.js` 與 `data/valuation_targets.json`。
- 主要以 2028E／FY2029E 的獲利能力與高檔合理倍數，建立**樂觀但需條件成立**的中期估值上緣。
- 不是券商共識、不是機率加權目標，也不是保證報酬。
- 網站每日只更新價格，**不會自動調高理想價**，避免股價上漲後目標價同步上修造成循環論證。

網站中的「編輯理想價」會將修改值儲存在該瀏覽器的 `localStorage`。要讓所有訪客共用新目標：

1. 在網站按「編輯理想價」並儲存；
2. 按「下載 targets.js」；
3. 用下載檔取代 repository 的 `data/valuation_targets.js`；
4. commit 後重新部署。

## 本機手動更新

```bash
python -m pip install -r requirements.txt
python scripts/update_prices.py
```

更新完成後，重新整理 `index.html`。若直接以 `file://` 開啟時瀏覽器限制跨檔讀取，可在資料夾內啟動簡易伺服器：

```bash
python -m http.server 8000
```

再開啟 `http://localhost:8000/`。

## 調整更新頻率

排程位於 `.github/workflows/deploy-and-update.yml`：

```yaml
schedule:
  - cron: "45 22 * * 1-5"
```

目前為每個平日一次。若只需手動或不定期更新，可移除 `schedule` 區塊並保留 `workflow_dispatch`。

## 主要檔案

- `index.html`：完整互動網站
- `standalone_snapshot.html`：內建快照的單檔版
- `data/market_prices.js/json`：每日價格快照
- `data/valuation_targets.js/json`：理想價、估值基礎與成立條件
- `scripts/update_prices.py`：收盤價更新器
- `.github/workflows/deploy-and-update.yml`：定時更新與 GitHub Pages 部署
- `requirements.txt`：Python 套件版本範圍

## 風險聲明

免費行情可能延遲、缺漏、調整錯誤或因供應商介面變動而失效；交易前應以交易所或券商資料確認。理想價高度依賴 EPS、估值倍數、design win、產品量產與產業資本支出假設，尤其 NVTS、AOSL、康舒與群電等轉型情境的落差可能非常大。
