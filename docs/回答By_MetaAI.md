回答By_MetaAI
対象: Ink Hub セカンドオピニオン / 黒井葉跡 様
回答日: 2026-05-24
回答者: Meta AI

1. 結論
PySide6 + QtWebEngineへの移行を推奨
理由：Ink Hubの核心価値「マルチサービス一元化」を守るには、Googleログインの確実性とセッション分離の簡潔さが必須。Tauri v2継続は技術的負債とプロダクト価値毀損のリスクが高い。

2. 現状の技術的課題評価
課題

評価

詳細

Tauri v2 <webview>廃止

仕様

バグではなく機能削除。黒画面はコンテンツブロックによる正常動作

Ubuntu 24.04 + Googleログイン

重大

WebKitGTKはUA偽装してもnavigator.userAgentDataとTLS fingerprintで検出・ブロックされる

WebviewWindow重ね込み

高コスト

座標同期、Z-order、クリック透過、Wayland対応を自前実装。Tauriの「軽量」メリットが相殺される

webkit2gtk-4.1依存

不安定

GoogleのWebKitGTK排除傾向が強く、将来ブロックリスクが継続

判定: Tauri v2 + WebKitGTKの組み合わせは、Ink Hubの要件に対して構造的に不利。

3. 選択肢比較：PySide6 vs Tauri継続
項目

PySide6 + QtWebEngine

Tauri v2 + WebviewWindow

重要度

Googleログイン

◎ 完璧。Chromeと同一

△ 一時的に通るが将来ブロック高

極高

セッション分離

◎ QWebEngineProfile1行で完全分離

△ data_directory設定、分離不完全

高

実装難易度

中。WebView埋め込みはQt標準機能

高。重ね込み管理を自前実装

中

バイナリサイズ

80-120MB

15-25MB

低

メモリ 10WebView時

1.0-1.5GB

0.8-1.2GB

中

LLM統合

◎ Pythonエコシステムが豊富

△ Rust実装が必要

中

既存資産活用

❌ React/TS/Zustand要書き直し

✅ そのまま

中

長期的安定性

◎ Chromiumベースで安定

△ WebKitGTKブロックリスク継続

高

総評: 「軽量」以外の全項目でPySide6が優位。特にGoogle系サービス非対応は「マルチサービス一元化」の看板を降ろすことと同義。

4. 既存資産を捨てるコストの評価
失うもの: React/TSコンポーネント、Zustand状態管理、TailwindCSS、Rustバックエンド
得るもの: Googleログイン確実性、セッション分離の簡潔性、LLM統合速度、Wayland安定性

判断: 短期的には書き直しコストが発生するが、TauriでGoogleブロックと戦い続ける長期的コストの方が大きい。今痛みを受け入れて移行する方が総工数は少ない。

5. 推奨移行計画
フェーズ1：技術検証 / 1週間

PySide6 + QtWebEngineでGmail/YouTube/Notion同時ログインPoC
セッション分離動作確認
Ubuntu 24.04でのAppImage/debビルド確認
→ ここでコケたらTauri継続を再検討
フェーズ2：UI再構築 / 2週間

左サイドバー、サービス登録モーダルをPySide6移植
Zustandの設計思想をPythonクラス構造へ移行
Qt StyleSheetでTailwindのUI感覚を再現
フェーズ3：機能統合 / 1週間

LLMバックエンド選択UI実装
設定JSON互換性維持
ファビコン自動取得移植
フェーズ4：テスト・リリース / 1週間

マルチサービス同時表示の安定性確認
パッケージング・配布
6. Tauri継続を選ぶ場合の条件
以下の4点を全て受容できる場合のみ現実的：

Google系は諦める：外部Chromeで開く方式に変更。OAuth PKCE + API連携に割り切る
WebviewWindow実装を完遂：座標・Z-order・Wayland対応を自前で完全に制御
webkit2gtkと心中する：Googleのブロック強化に追従し続ける覚悟
プロダクト定義を変更：「ブラウザ統合」ではなく「APIクライアント統合」と再定義
7. 追加リスクと留意点
QtWebEngineライセンス: LGPL v3。AppImage配布なら問題ないが、改変・静的リンク時はソース開示義務あり。法務確認推奨
Wayland問題: Qtでも発生しうるが、QWebEngineViewが大部分を吸収。Tauriの手動重ね込みより安定
「軽量」の再定義: バイナリ100MBを嫌うユーザー < Googleログイン不可を嫌うユーザー。必要ならLite版をTauriで別ライン化
8. 最終判断
Ink Hubが「全サービスを1つのUIに入れる家」であるなら、Google部屋に入れない家は欠陥住宅になる。

現時点の情報に基づく限り、PySide6移行が最適解。
React資産の書き直しは痛いが、Googleと戦い続ける慢性的な痛みよりはマシ。

ただし、事業として「軽量・Rust・モダンスタック」がアイデンティティで、Google系を切り捨てても成立するならTauri継続も論理的には成立する。最終判断はプロダクトの提供価値の定義次第。