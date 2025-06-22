# 🧠 プロジェクト構想：「インタラクティブ鳥類クレードグラム」

## ✅ 目的

* すべての現生鳥類（Aves）を系統分類（クラス・目・科・属・種）に基づき、視覚的に整理
* ユーザーがズームレベルに応じて分類階層の「ざっくり → 細かく」な変化を確認できるようにする

---

## 🏗️ 全体構成

### 🔹 フロントエンド（Next.js + D3.js or Recharts + React Flow）

* 検討ライブラリ：

  * `react-d3-tree`: クレードグラム向き（ツリー構造）
  * `React Flow`: ノードとエッジの自由な構造可視化に強い
* 機能:

  * クレードノードのズーム・パン（zoom & pan）
  * ズームレベルに応じて表示粒度切替（例：Class → Order → Family → Genus/Species）
  * 検索バーによる特定種のハイライト・フォーカス
  * ホバー時に分類情報や画像表示（Wikipedia API連携可）

### 🔹 バックエンド（Supabase）

* SupabaseのPostgreSQLに以下の構造で分類情報を保存

### 🔸 テーブル設計案 `bird_taxonomy`

#### フィールド定義

| フィールド名            | 型                 | 説明                                            |
| ----------------- | ----------------- | --------------------------------------------- |
| `id`              | `uuid` (PK)       | 一意な識別子                                        |
| `name`            | `text`            | 表示名（通常は分類名）                                   |
| `rank`            | `text`            | 分類階級（例: class, order, family, genus, species） |
| `parent_id`       | `uuid` (FK)       | 親ノードのID（nullならroot）                           |
| `scientific_name` | `text` (nullable) | 学名（種や属などで必要）                                  |
| `common_name`     | `text` (nullable) | 一般名（例: birds, crows）                          |
| `wikipedia_url`   | `text` (nullable) | WikipediaページURL                               |
| `image_url`       | `text` (nullable) | 種などの画像URL（Wikidataなどから取得）                     |
| `created_at`      | `timestamp`       | 作成日時                                          |
| `updated_at`      | `timestamp`       | 更新日時                                          |

#### SQL作成例

```sql
create table bird_taxonomy (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  rank text check (rank in ('class', 'order', 'family', 'genus', 'species')) not null,
  parent_id uuid references bird_taxonomy(id) on delete cascade,
  scientific_name text,
  common_name text,
  wikipedia_url text,
  image_url text,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now()
);
```

---

## 🔁 ズームレベル仕様案

| ズームレベル | 表示ノード   | 例                    |
| ------ | ------- | -------------------- |
| 1（最小）  | Class   | Aves                 |
| 2      | Order   | Passeriformes        |
| 3      | Family  | Corvidae, Tyrannidae |
| 4      | Genus   | Corvus, Tyrannus     |
| 5（最大）  | Species | *Corvus corax* etc.  |

---

## ⚙️ 技術スタック案

| 分類     | 技術                                              |
| ------ | ----------------------------------------------- |
| フロント   | Next.js, React Flow or D3                       |
| バックエンド | Supabase (PostgreSQL + Edge Functions)          |
| データ収集  | Python + BeautifulSoup / SPARQL / Wikipedia API |
| デプロイ   | Vercel or Cloudflare Pages + Supabase           |

---

## ✨ ユーザー操作フロー

1. 初期ロード：`/api/clade?level=1` → Classのみ表示（Aves）
2. ユーザーがズーム → `/api/clade?level=2&parent=1` でOrderをロード
3. ノードをクリック → 子ノード展開、種の画像 or Wikiカード表示
4. 検索バーに「crow」 → 該当属/種にジャンプ、背景ハイライト

---

## 💡 次にやるべきステップ

1. **分類データ構造のスケルトンを作る**
2. **PythonでWikipediaから鳥類クレード情報を取得するスクリプト作成**
3. **Supabaseスキーマ定義と初期データ投入**
4. **Next.js + React Flow の動作確認（サンプルデータで）**
5. **ズームレベル切り替えロジック設計とAPI連携**
