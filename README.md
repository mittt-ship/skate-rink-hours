# skate-rink-hours

首都圏＋栃木・山梨の指定スケート場15施設について、一般営業（一般滑走）の時間を1日3回取得し、スマホで見られる一覧にするための仕組みです。

- 画面：`docs/index.html`（GitHub Pages で公開）
- 取得：`scripts/fetch.py`（`.github/workflows/update.yml` が日本時間 5時・12時・18時に実行）
- データ：`docs/data/`（今日〜翌月末を毎回更新、過去分は約14か月保存）
- 施設の一覧：`skate/rinks.py`
- 日光霧降の手入力：Googleスプレッドシート（列：rink_id, date, start, end, status, note）

表示内容は公式サイトの情報をもとにしていますが、AIの読み取りや基本営業時間からの「予定」を含みます。お出かけ前に必ず各施設の公式サイトで確認してください。
