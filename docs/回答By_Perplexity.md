回答By_Perplexity
セカンドオピニオンの完成版です。
結論としては、Tauri継続は可能だが、要件を優先するなら PySide6 + QtWebEngine のほうが成功率が高いです。PySide6 の QWebEngineProfile はサービスごとのセッション分離に使える公式クラスで、Tauri 側も WebviewWindow 系の設計で動かせますが、WebviewWindow は別窓制御の設計になり、実装と運用が重くなりやすいです 。
doc.qt
+1

重要な論点
Tauri v2 では、<webview> を前提にした設計ではなく、WebviewWindow ベースで考えるのが前提です 。
v2.tauri

PySide6 の QWebEngineProfile は、Web ページのプロファイルを分けるための公式機能で、セッション分離の設計に向いています 。
doc.qt

Ubuntu 24.04 周辺では WebKitGTK を使う埋め込みブラウザでログインや表示に問題が出る例があり、Google 系サービスとの相性を重く見るべきです 。
reddit
+2

判断の軸
観点	PySide6 + QtWebEngine	Tauri v2
Googleログイン	安定しやすい	方式次第で不安定
セッション分離	シンプル	設計と管理が重い
既存 React/TS 資産	捨てるコストあり	活かしやすい
軽量性	やや重い	軽い
長期安定性	高い	WebKitGTK 依存の不確実性あり
私の意見
この報告書の価値は、Tauri に残る理由が軽量性だけなら、優先順位を見直したほうがいいと示している点にあります。
Ink Hub の中心が「複数サービスを一元化して、実際にログインして使えること」なら、UI の軽さより基盤の確実性を取るのが自然です。

実務的な提案
まず PySide6 で PoC を作る。

Google ログインとセッション分離が安定するか確認する。

そのうえで、React/TS の資産をどこまで移植するか決める。

Tauri 継続案は、Google 連携を API/OAuth 寄りに割り切れる場合だけ残す。