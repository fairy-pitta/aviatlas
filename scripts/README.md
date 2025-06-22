# eBird Taxonomy to Supabase Converter

このスクリプトは、eBirdの分類データ（CSV）をSupabaseのPostgreSQLデータベースに変換・インポートするためのツールです。

## 🚀 セットアップ

### 1. 依存関係のインストール

```bash
pip install -r requirements.txt
```

### 2. 環境変数の設定

`.env`ファイルにSupabaseの認証情報を追加してください：

```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
```

**重要**: `SUPABASE_SERVICE_ROLE_KEY`は以下の手順で取得してください：
1. Supabaseダッシュボードにログイン
2. プロジェクト設定 → API
3. "service_role" キーをコピー

### 3. Supabaseテーブルの作成

スクリプトを実行すると、以下のSQLが表示されます。これをSupabaseのSQL Editorで実行してください：

```sql
CREATE TABLE IF NOT EXISTS bird_taxonomy (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    rank TEXT CHECK (rank IN ('class', 'order', 'family', 'genus', 'species')) NOT NULL,
    parent_id UUID REFERENCES bird_taxonomy(id) ON DELETE CASCADE,
    scientific_name TEXT,
    common_name TEXT,
    ebird_code TEXT,
    wikipedia_url TEXT,
    image_url TEXT,
    order_name TEXT,
    family_name TEXT,
    species_group TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- インデックスの作成
CREATE INDEX IF NOT EXISTS idx_bird_taxonomy_rank ON bird_taxonomy(rank);
CREATE INDEX IF NOT EXISTS idx_bird_taxonomy_parent_id ON bird_taxonomy(parent_id);
CREATE INDEX IF NOT EXISTS idx_bird_taxonomy_ebird_code ON bird_taxonomy(ebird_code);
CREATE INDEX IF NOT EXISTS idx_bird_taxonomy_scientific_name ON bird_taxonomy(scientific_name);
```

## 📊 使用方法

### スクリプトの実行

```bash
cd /Users/shuna/aviatlas
python scripts/convert_ebird_to_supabase.py
```

### 処理の流れ

1. **CSVファイルの読み込み**: eBird taxonomy CSVを解析
2. **階層構造の構築**: Class → Order → Family → Genus → Species の階層を作成
3. **テーブル作成SQL表示**: 手動でSupabaseに実行する必要があります
4. **データのインサート**: 階層順序でデータをSupabaseに挿入

## 🏗️ データ構造

### 入力データ（eBird CSV）

| フィールド | 説明 |
|-----------|------|
| TAXON_ORDER | 分類順序 |
| CATEGORY | カテゴリ（species, genus等） |
| SPECIES_CODE | eBird種コード |
| PRIMARY_COM_NAME | 主要な一般名 |
| SCI_NAME | 学名 |
| ORDER | 目 |
| FAMILY | 科 |
| SPECIES_GROUP | 種グループ |

### 出力データ（Supabase）

階層構造のテーブル：
- **Class**: Aves（鳥類）
- **Order**: Passeriformes, Falconiformes等
- **Family**: Corvidae, Tyrannidae等
- **Genus**: Corvus, Tyrannus等
- **Species**: 個別の種

## ⚠️ 注意事項

1. **大量データ**: 17,000+行のデータを処理するため、時間がかかります
2. **Service Role Key**: 管理者権限が必要なため、適切に保護してください
3. **重複処理**: スクリプトは重複を避けるロジックを含んでいます
4. **エラーハンドリング**: バッチ処理でエラーが発生しても継続します

## 🔧 カスタマイズ

### バッチサイズの調整

```python
batch_size = 100  # デフォルト値、必要に応じて調整
```

### フィルタリング

現在は`species`カテゴリのみを処理していますが、他のカテゴリも含める場合：

```python
# Skip non-species entries for now (focus on species only)
if row['CATEGORY'] not in ['species', 'genus', 'family']:  # 例：複数カテゴリを許可
    continue
```

## 🐛 トラブルシューティング

### よくあるエラー

1. **認証エラー**: Service Role Keyが正しく設定されているか確認
2. **テーブル未作成**: SQLを手動で実行したか確認
3. **ネットワークエラー**: Supabaseプロジェクトがアクティブか確認

### ログの確認

スクリプトは進行状況を表示します：
```
Processed 1000 rows...
Built taxonomy tree with 15234 nodes
Inserting 1 class nodes...
Inserting 40 order nodes...
```

## 📈 パフォーマンス

- **処理時間**: 約5-10分（データサイズによる）
- **メモリ使用量**: 約100-200MB
- **ネットワーク**: バッチ処理により効率化

## 🔄 更新

新しいeBirdデータで更新する場合：
1. 既存テーブルをクリア（必要に応じて）
2. 新しいCSVファイルでスクリプトを再実行

```sql
-- テーブルクリア（注意：全データが削除されます）
TRUNCATE TABLE bird_taxonomy RESTART IDENTITY CASCADE;
```