# Gemini Sparkへの導入

このフォルダをZIP化した配布ファイルを、Gemini SparkのSkills画面からアップロードする。

## 導入手順

1. 個人のGoogleアカウントでGeminiを開き、Sparkへ切り替える。
2. `Skills` → `Upload` を選ぶ。
3. `build-complete-manga-lp-gemini-spark.zip` を選ぶ。
4. 名前・説明・指示を確認し、`Create` を押す。
5. Mac版SparkでLPを完成させる場合は、出力先フォルダだけをConnected folderへ追加する。
6. タスクで `/build-complete-manga-lp` を選ぶか、「漫画LP完成ビルダーを使って」と依頼する。

## 必要条件

- Gemini SparkのSkillsを利用できる個人アカウントと対象プラン
- 完成データをローカル生成する場合はMac版Spark
- Mac側で `python3` とPillowが利用可能であること
- 商品URL、商品資料、CTA URL、必要な参照画像

## 安全

- Connected folderは案件用フォルダだけを指定する。
- 秘密鍵、決済情報、顧客の個人情報をタスクや接続フォルダへ置かない。
- 既存データの削除や外部共有は、このスキルの工程に含めない。

## 制限

Web版・モバイル版でローカルコマンドやPNG保存が使えない場合、ネームと画像プロンプトまでは作れるが、完成ZIPの生成にはMac版Sparkが必要になる。
