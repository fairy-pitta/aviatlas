# Wikipedia and Image URL Update Scripts

このディレクトリには、鳥類分類データベースにWikipediaのURLと画像URLを自動的に追加するためのスクリプトが含まれています。

## スクリプト概要

### 1. `simple_wiki_update.py` - シンプルな更新スクリプト

**用途**: 少数の種（1-100種程度）を安全に更新する場合

**特徴**:
- 安定性重視の設計
- 詳細なログ出力
- エラーハンドリングが充実
- ドライランモード対応

**使用例**:
```bash
# ドライランでテスト（データベースを変更しない）
python3 scripts/simple_wiki_update.py --dry-run --limit 10

# 実際に50種を更新
python3 scripts/simple_wiki_update.py --limit 50

# 詳細ログ付きで100種を更新
python3 scripts/simple_wiki_update.py --limit 100 --verbose

# 特定のオフセットから開始
python3 scripts/simple_wiki_update.py --limit 50 --offset 1000
```

### 2. `mass_wiki_update.py` - 大規模更新スクリプト

**用途**: 大量の種（数千種）を効率的に更新する場合

**特徴**:
- バッチ処理による効率化
- 進行状況の保存と復旧機能
- 中断・再開が可能
- バッチサイズの調整可能

**使用例**:
```bash
# ドライランでテスト
python3 scripts/mass_wiki_update.py --dry-run --batch-size 25 --max-batches 2

# 実際に大規模更新（バッチサイズ100、最大10バッチ）
python3 scripts/mass_wiki_update.py --batch-size 100 --max-batches 10

# 全種を更新（中断・再開可能）
python3 scripts/mass_wiki_update.py --batch-size 200

# 進行状況を確認
python3 scripts/mass_wiki_update.py --status

# 最初からやり直し
python3 scripts/mass_wiki_update.py --start-fresh
```

### 3. `check_wiki_images.py` - 状況確認スクリプト

**用途**: データベースの更新状況を確認

**使用例**:
```bash
python3 scripts/check_wiki_images.py
```

## 推奨使用手順

### 初回セットアップ

1. **依存関係のインストール**:
   ```bash
   pip3 install -r requirements.txt
   ```

2. **環境変数の設定**:
   `.env`ファイルに以下を設定:
   ```
   NEXT_PUBLIC_SUPABASE_URL=your_supabase_url
   SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
   ```

### 小規模テスト

1. **ドライランでテスト**:
   ```bash
   python3 scripts/simple_wiki_update.py --dry-run --limit 5
   ```

2. **少数の種で実際にテスト**:
   ```bash
   python3 scripts/simple_wiki_update.py --limit 10
   ```

3. **結果を確認**:
   ```bash
   python3 scripts/check_wiki_images.py
   ```

### 大規模更新

1. **段階的に実行**:
   ```bash
   # 最初は少ないバッチ数で
   python3 scripts/mass_wiki_update.py --batch-size 100 --max-batches 5
   
   # 問題なければ継続
   python3 scripts/mass_wiki_update.py --batch-size 100 --max-batches 20
   
   # 最終的に全種を処理
   python3 scripts/mass_wiki_update.py --batch-size 200
   ```

2. **定期的に進行状況を確認**:
   ```bash
   python3 scripts/mass_wiki_update.py --status
   python3 scripts/check_wiki_images.py
   ```

## パラメータ説明

### 共通パラメータ

- `--dry-run`: データベースを変更せずにテスト実行
- `--verbose`: 詳細なログを出力
- `--limit N`: 処理する種の数を制限

### simple_wiki_update.py 固有

- `--offset N`: 処理開始位置を指定

### mass_wiki_update.py 固有

- `--batch-size N`: 1バッチあたりの種数（デフォルト: 100）
- `--max-batches N`: 最大バッチ数を制限
- `--start-fresh`: 進行状況をリセットして最初から開始
- `--status`: 現在の進行状況を表示

## ログファイル

- `simple_wiki_update.log`: シンプル更新スクリプトのログ
- `mass_wiki_update.log`: 大規模更新スクリプトのログ
- `mass_update_progress.json`: 大規模更新の進行状況（自動生成・管理）

## 注意事項

1. **レート制限**: Wikipedia APIに負荷をかけないよう、リクエスト間に0.5秒の間隔を設けています

2. **中断と再開**: `mass_wiki_update.py`は中断されても進行状況を保存し、再実行時に続きから処理を開始します

3. **エラーハンドリング**: ネットワークエラーやAPI制限に対して適切に対処し、処理を継続します

4. **データベース接続**: Supabaseの認証情報が正しく設定されていることを確認してください

## トラブルシューティング

### よくある問題

1. **Supabase接続エラー**:
   - `.env`ファイルの認証情報を確認
   - ネットワーク接続を確認

2. **Wikipedia API エラー**:
   - インターネット接続を確認
   - しばらく待ってから再実行

3. **依存関係エラー**:
   ```bash
   pip3 install -r requirements.txt
   ```

### ログの確認

詳細なエラー情報はログファイルで確認できます:
```bash
tail -f simple_wiki_update.log
tail -f mass_wiki_update.log
```

## 処理統計の例

成功時の出力例:
```
============================================================
WIKIPEDIA AND IMAGE UPDATE SUMMARY
============================================================
Total processed: 100
Wikipedia URLs found: 95
Image URLs found: 88
Successfully updated: 100
Errors: 0
Skipped (no data found): 0
Success rate: 100.0%
============================================================
```

## 開発者向け情報

### アーキテクチャ

- `SimpleWikiUpdater`: 基本的な更新機能を提供するクラス
- `MassWikiUpdater`: 大規模処理用の拡張クラス
- Wikipedia REST API と MediaWiki API を併用
- Supabase Python クライアントを使用

### 拡張可能性

- 他の画像ソース（Flickr、iNaturalist等）の追加
- 並列処理の実装
- より高度なマッチングアルゴリズム
- 画像品質の自動評価