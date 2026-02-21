# ぴよログ Home Assistant 統合

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

[ぴよログ](https://www.piyolog.com/) の Home Assistant 統合です。

## 機能

- アカウントの作成と既存アカウントへのリンク
- 排泄・睡眠・授乳などのぴよログイベントの登録
- ぴよログへのイベント登録時のHome Assistantイベントトリガの発火
- イベントの最終登録時刻を保持するセンサ
- 本日の授乳の合計時間を保持するセンサ

## インストール

### HACS（推奨）

1. Home Assistant で HACS を開く
2. 右上の「⋯」をクリック
3. 「カスタムリポジトリ」を選択
4. 統合として `https://github.com/naoki-mizuno/piyolog-hacs` を追加
5. ぴよログのカードで「インストール」をクリック
6. Home Assistant を再起動する

### 手動インストール

1. `custom_components/piyolog` フォルダを `config/custom_components/` にコピーする
2. Home Assistant を再起動する

## セットアップ

### 方法1: 新規作成＆リンク（推奨）

新しいデバイス（アカウント）としてぴよログに登録します。

1. **設定 → デバイスとサービス → 統合を追加** を開く
2. 「PiyoLog」で検索する
3. **「新規アカウントを作成して既存アカウントにリンク」** を選択する
4. デバイス名を入力（例：「Home Assistant」）
5. スマホのぴよログアプリで：
   - **設定 → アカウント → 共有用コードを発行** を開き、 **共有用コードの取得** を押す
   - ぴよログID と 共有コード が表示される
6. Home Assistant にユーザーID と 共有コード を入力する
7. デフォルトの赤ちゃんを選択する

### 方法2: 既存の認証情報を登録

別環境からの移行や、すでに認証情報を持っている場合に使います。

1. **設定 → デバイスとサービス → 統合を追加** を開く
2. 「PiyoLog」で検索する
3. **「既存の認証情報を使用」** を選択する
4. `user_id`、`client_id`、`client_token` を入力する
5. デフォルトの赤ちゃんを選択する

## サービス

すべてのサービスは `piyolog` ドメインで利用できます。

### 共通パラメータ

全サービスで以下のオプション引数が使えます：

| パラメータ   | 型      | 説明                                           | 例                                   |
| ------------ | ------- | ---------------------------------------------- | ------------------------------------ |
| `baby_id`    | string  | 対象の赤ちゃんID（デフォルトを上書き）         | `"abc123def456"`                     |
| `baby_index` | integer | 赤ちゃんのインデックス（0始まり）              | `0`                                  |
| `datetime`   | string  | イベント日時（ISO・相対・Unix タイムスタンプ） | `"2026-02-09T14:30:00"` や `"5分前"` |
| `memo`       | string  | 任意のメモ・コメント                           | `"ごきげん"`                         |

### サービス一覧

注意：ぴよログで登録できる全てのイベントが実装されているわけではありません。

#### `piyolog.add_pee`

「おしっこ」を登録します。

```yaml
service: piyolog.add_pee
data:
  memo: "嫌がっていた"
  datetime: "5分前" # 任意：デフォルトは現在時刻、dateparserがパースできる文字列
```

#### `piyolog.add_poo`

「うんち」を登録します。詳細パラメータも指定できます。

**基本的な使い方：**

```yaml
service: piyolog.add_poo
data:
  memo: "あふれそうだった"
```

**詳細パラメータ付き：**

```yaml
service: piyolog.add_poo
data:
  poo_amount: "normal" # default, bit, small, normal, large
  poo_hardness: "normal" # default, diarrhea, soft, normal, hard
  poo_color: "brown" # default, white, yellow, orange, brown, green, red, black
  memo: "ごきげんになった"
  datetime: "10 minutes ago"
```

**うんちパラメータ一覧：**

| パラメータ     | 値（value）                                                                                                          | 説明       |
| -------------- | -------------------------------------------------------------------------------------------------------------------- | ---------- |
| `poo_amount`   | `default`=記録なし<br>`bit`=ちょこっと<br>`small`=少なめ<br>`normal`=ふつう<br>`large`=多め                          | 量         |
| `poo_hardness` | `default`=記録なし<br>`diarrhea`=下痢<br>`soft`=やわらかめ<br>`normal`=ふつう<br>`hard`=かため                       | 硬さ・状態 |
| `poo_color`    | `default`=記録なし<br>`white`=白<br>`yellow`=黄<br>`orange`=橙<br>`brown`=茶<br>`green`=緑<br>`red`=赤<br>`black`=黒 | 色         |

#### `piyolog.add_pee_and_poo`

おしっことうんちを同時に登録します（同じ日時）。うんちの詳細パラメータも指定可能です。

```yaml
service: piyolog.add_pee_and_poo
data:
  poo_amount: "large" # 多め
  poo_hardness: "normal" # ふつう
  poo_color: "brown" # 茶色
  memo: "いつもと違う"
```

#### `piyolog.add_sleep`

「寝る」を登録します。

```yaml
service: piyolog.add_sleep
data:
  memo: "お昼寝"
  datetime: "2026-02-09T13:00:00"
```

#### `piyolog.add_wake_up`

「起きる」を登録します。

```yaml
service: piyolog.add_wake_up
data:
  memo: "ごきげんに起きた"
```

#### `piyolog.add_milk`

「ミルク」を登録します。

```yaml
service: piyolog.add_milk
data:
  amount: 120 # ml（省略時は 100）
  memo: "ミルク"
```

#### `piyolog.add_breastfeeding`

「母乳」を登録します。左右の時間・順番・授乳量（任意）を指定できます。

```yaml
service: piyolog.add_breastfeeding
data:
  breastfeeding_left_minutes: 10 # 左の時間（分）
  breastfeeding_right_minutes: 8 # 右の時間（分）
  breastfeeding_order: "left_first" # unspecified, left_first, right_first
  amount: 80 # 任意：授乳量（ml）
  memo: "よく飲んだ"
```

**授乳順番（breastfeeding_order）：**

| 値            | 説明     |
| ------------- | -------- |
| `unspecified` | 指定なし |
| `left_first`  | 左→右    |
| `right_first` | 右→左    |

#### `piyolog.add_bath`

「お風呂」を登録します。

```yaml
service: piyolog.add_bath
data:
  memo: "夜のお風呂"
```

#### `piyolog.add_walk`

「さんぽ」を登録します。

```yaml
service: piyolog.add_walk
data:
  memo: "公園でお散歩"
  datetime: "yesterday 3pm" # 相対時間にも対応
```

#### `piyolog.force_sync`

ぴよログAPIと即時同期します。通常は設定した同期間隔で自動同期されますが、必要なときに手動で呼び出せます。パラメータは不要です。

```yaml
service: piyolog.force_sync
```

## オートメーション例

### ボタン押下でイベント登録

```yaml
automation:
  - alias: "おしっこボタン"
    trigger:
      - platform: state
        entity_id: input_button.baby_pee
    action:
      - service: piyolog.add_pee
        data:
          memo: "ボタンで登録"
```

### 時間ベースのリマインダー

```yaml
automation:
  - alias: "授乳リマインダー"
    trigger:
      - platform: time_pattern
        hours: "/3" # 3時間ごと
    action:
      - service: notify.mobile_app
        data:
          message: "授乳の時間です！"
      # 任意：自動で授乳を記録
      - service: piyolog.add_milk
        data:
          amount: 100
          memo: "定時授乳"
```

### 複数赤ちゃん：特定の赤ちゃんを指定

```yaml
service: piyolog.add_pee
data:
  baby_index: 0 # 1人目
  memo: "双子Aのおしっこ"
```

## 設定

### 同期間隔

セットアップ後、同期間隔を変更できます。

1. **設定 → デバイスとサービス** を開く
2. 「PiyoLog」→ **設定** をクリック
3. 同期間隔を設定（30〜300秒、デフォルト: 30）

**手動で即時同期したい場合**は、サービス `piyolog.force_sync` を呼び出してください。オートメーションやスクリプトからも利用できます。

**注意:** 30秒より短い間隔での同期は、APIサーバーへの負荷が大きくなるため推奨しません。

## 複数赤ちゃん対応

ぴよログアカウントに複数の赤ちゃんがいる場合：

1. セットアップ時に **デフォルトの赤ちゃん** を選択
2. サービスごとに `baby_id` または `baby_index` で上書きできます：

```yaml
# インデックスで指定（0始まり）
service: piyolog.add_pee
data:
  baby_index: 0      # 1人目

# または赤ちゃんIDで指定
service: piyolog.add_pee
data:
  baby_id: "abc123def456"
```

### デバッグログ

統合のカード内メニューからデバッグ出力を有効化するか、 `configuration.yaml` に以下を追加します：

```yaml
logger:
  default: info
  logs:
    custom_components.piyolog: debug
```

**設定 → システム → ログ** で確認してください（Home Assistantの再起動が必要な
場合があります）。

## センサの活用例

各イベント種別（`const.py` の `EVENT_TYPE_NAMES` を参照）に対応したセンサが自動的に作成されます。センサIDは `sensor.piyolog_most_recent_<event_type>_<baby_name>` の形式です。

**設定 → Developer Tools → States** の Filter Entities に、 `piyolog` と入力することで、センサの値と属性を確認することができます。

### 最後のイベントからの経過時間を読み上げる

```yaml
alias: 最後のミルクを言う
description: ""
triggers: []
conditions: []
actions:
  - variables:
      event_type: milk
      baby_name: hogehoge
  - action: tts.speak
    target:
      entity_id: tts.google_translate_en_com
    data:
      media_player_entity_id: media_player.my_speaker
      message: >
        {% set sensor_id = 'sensor.piyolog_most_recent_' ~ event_type ~ '_' ~
        baby_name %} {% set last_time = states(sensor_id) | as_datetime %}

        {% if last_time %}
          {% set delta = now() - last_time %}
          {% set total_seconds = delta.total_seconds() | int %}
          {% set hours = total_seconds // 3600 %}
          {% set minutes = (total_seconds % 3600) // 60 %}
          
          {% if hours > 0 %}
            {{ hours }}時間{{ minutes }}分前です。
          {% else %}
            {{ minutes }}分前です。
          {% endif %}
        {% else %}
          そのイベントは登録されていません。
        {% endif %}
      language: ja
mode: single
```

### 授乳の左右バランスを読み上げる

Home Assistantで設定しているタイムゾーンにおける、その日に授乳した左右の時間を合計し、どちらが短いかをアナウンスします。左右のどちらから授乳するかの判断に役立ちます。

センサIDは `sensor.piyolog_breastfeeding_today_<baby_name>` です。

```yaml
alias: 授乳の情報を言う
description: ""
triggers: []
conditions: []
actions:
  - variables:
      baby_name: hogehoge
  - action: tts.speak
    target:
      entity_id: tts.google_translate_en_com
    data:
      media_player_entity_id: media_player.my_speaker
      message: >
        {% set sensor_id = 'sensor.piyolog_breastfeeding_today_' ~ baby_name %}
        {% set left = state_attr(sensor_id, 'left_minutes') | int(0) %} {% set
        right = state_attr(sensor_id, 'right_minutes') | int(0) %}

        {% if right > left %}
          {% set delta = right - left %}
          左の方が{{ delta }}分、授乳時間が短いです。
        {% elif left > right %}
          {% set delta = left - right %}
          右の方が{{ delta }}分、授乳時間が短いです。
        {% else %}
          どちらも同じ時間、授乳しています。
        {% endif %}

        {% set count = state_attr(sensor_id, 'session_count') | int(0) %}
        授乳回数は{{ count }}回です。
      language: ja
mode: single
```

## サポート

- **不具合・要望:** [GitHub Issues](https://github.com/naoki-mizuno/piyolog-hacs/issues)
- **質問・議論:** [GitHub Discussions](https://github.com/naoki-mizuno/piyolog-hacs/discussions)

## ライセンスと注意事項

MIT License - 詳細は [LICENSE](LICENSE) を参照してください。

教育・研究目的での使用に限ります。

**ぴよログAPIサーバに負荷をかけないよう、リクエスト送信時には注意してください。**
