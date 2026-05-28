Ink Boss：開発部管理型・完全ローカルアクティベーション設計書1. 基本設計思想（開発部のガバナンス ＆ Human Care）ライバーが「Ink Boss」を導入する際の認知負荷（新しいサービスへの登録、APIキーの設定など）を完全にゼロにし、ダウンロードして即戦力として使える手軽さを提供します。同時に、XやGmailなどの機密情報はすべてライバー個人のPC（ローカル）に閉じ込め、開発部が管理するネットワーク上には「アプリの起動許可フラグ」のみを配置することで、プライバシーの保護と退所後のアクセス制御を完璧に両立させます。2. アーキテクチャ概要図[ ライバーのPC（Ink Boss / Windows 11） ]       [ 開発部管理サーバー（GitHub等） ]
                  │                                             │
                  ├─ ① 起動：ライバーIDを照合 ───────────────>│
                  │                                             │ (リスト内検索)
                  │<─ ② 応答：アクティブ状態（許可） ──────────┤
                  │                                             │
      (pywebview起動成功)                                       │
                  │                                             │
     ┌────────────┴────────────┐                                │
     │ 【完全ローカル処理】   │                                │
     │  ・config.json (設定)   │                                │
     │  ・SQLite / セッション  │                                │
     └─────────────────────────┘                                │
     ※ 各サービスのログイン情報やCookieは、開発部サーバーへ一切送信されません。
3. 2つのコア・ロジック① 開発部による「生存シグナル（門番）」システム開発部が管理するパブリックな領域（GitHub Pages、または一般公開に設定したNotionの1ページ、開発部所有のレンタルサーバーなど）に、現在所属している有効なライバーのIDを記録した1枚のテキストファイル（JSON形式）を配置します。起動時の挙動: アプリ起動時、Pythonの標準ライブラリ（urllib.request）を使って、裏でこのテキストファイルを一瞬だけ読み込みにいきます。判定処理: 自身のアプリに埋め込まれている「ライバーID」がリストに存在すれば正常起動し、存在しなければ「このバージョンは現在利用できません」とダイアログを出して、WebView（メイン画面）を開かずに強制終了（sys.exit()）します。退所時のガバナンス: 開発部がテキストファイルから該当ライバーのIDを削除するだけです。1秒で世界中どこからでもアクセス権を剥奪できます。② Streamlitライクな「完全ローカル・データ保存」Ink Memory で使い慣れているローカル保存（SQLiteやJSON）のロジックをそのままInk BossのPythonバックエンドに移植します。保存場所: 各ライバーのPCのアプリケーションを実行しているディレクトリ（またはユーザーローカルの隔離フォルダ）に、config.json や ink_boss.db（SQLite）として自動生成されます。安全性: 外部データベースと一切通信を行わないため、ライバーが入力したXのアカウント名、URL、各種パスワード、LLMのプロンプト内容などが開発部側に筒抜けになるリスクが構造上100%排除されます。4. 開発部およびライバーのメリット比較項目Supabase等のクラウドDB方式新・開発部シグナル ＋ 完全ローカル方式ライバーの手間❌ アカウント作成やキーのコピペが必要⭕ ゼロ（EXEを起動するだけ）開発部の構築負荷🔺 DB構築、テーブル設計、接続エラー対策⭕ ほぼゼロ（ネット上にテキストを1枚置くだけ）データ漏洩リスク🔺 クラウドに送るため暗号化等に気を使う⭕ ゼロ（データがPCから外に出ない）インフラ維持コスト❌ 1週間未アクセスによる自動停止対策が必要⭕ 永続無料（サーバーが寝る心配がない）5. 開発部用：バックエンド（Python）実装コードモックInk Bossの main.py の最上部に組み込む、アクティベーションおよび強制終了の最小実装サンプルです。Pythonimport urllib.request
import json
import sys
from PySide6.QtWidgets import QApplication, QMessageBox

# 開発部が管理する「現役ライバーIDリスト」の公開URL
DEVELOPMENT_AUTH_URL = "https://raw.githubusercontent.com/ink-inc/auth/main/active_livers.json"

# ※ 各ライバーへ配布するEXEごとに、開発部側で書き換えてビルドする固有ID
MY_LIVER_ID = "liver_kuroi_001" 

def check_activation():
    """起動時に開発部のリストと照合する門番関数"""
    try:
        # 1. 開発部の最新リストを一瞬だけ読み込む
        req = urllib.request.Request(DEVELOPMENT_AUTH_URL, headers={'User-Agent': 'Ink-Boss-Client'})
        with urllib.request.urlopen(req, timeout=3) as response:
            allowed_livers = json.loads(response.read().decode('utf-8'))
            
        # 2. 自分のIDが開発部の許可リストにあるかチェック
        if MY_LIVER_ID not in allowed_livers:
            show_error_and_exit("認証エラー", "このアカウントは現在有効ではありません。開発部へお問い合わせください。")
            
    except Exception as e:
        # オフライン時や開発部サーバーが一時的にダウンしている場合の安全弁
        # セキュリティを高めるなら終了、利便性を取るならログを出して通過させる
        print(f"開発部認証サーバー通信エラー: {e}")
        # 安全側に倒して終了する場合:
        show_error_and_exit("通信エラー", "認証サーバーに接続できません。ネットワーク環境を確認してください。")

def show_error_and_exit(title, message):
    """ pywebview起動前にQtのダイアログでお知らせして安全に強制終了する """
    app = QApplication.instance() or QApplication([])
    QMessageBox.critical(None, title, message)
    sys.exit(1)

if __name__ == "__main__":
    # 1. まず開発部の門番チェックを通す
    check_activation()
    
    # 2. 通過した場合のみ、ローカルのJSON/SQLiteを読み込んでpywebviewを起動
    print("認証成功：Ink Bossを起動します。")
    # ここに通常の起動処理（webview.start...）を記述
6. 今後の開発部運用フロー新規ライバー入所時: 開発部が管理用テキストファイルに「新しいID」を1行追加。そのIDを埋め込んだEXE（または設定ファイル）をライバーに渡すだけで即座に利用可能。ライバー退所時: 開発部が管理用テキストファイルから該当IDを削除。以降、ライバーがアプリを起動しようとしてもWebViewが開く前に安全にシャットダウンされます。