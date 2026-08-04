# 出力契約

ジョブは必ず独立フォルダに作る。複数案件で `p001.png` が衝突しないよう、共有の素材フォルダへ直接出力しない。

```text
job/
├── brief.json
├── script.json
├── assets/
│   ├── characters/
│   └── panels/
├── reports/
│   ├── image_jobs.json
│   ├── image_jobs.md
│   ├── audit.json
│   └── manifest.json
└── output/
    ├── pages/page_01.png ...
    ├── lp.html
    ├── note_vertical.png
    ├── social/card_01.png ...
    └── manga-lp-delivery.zip
```

`lp.html` はページ画像をBase64で内包し、ローカル絶対パスを持たない。ZIPは破損検査でき、`manifest.json` は各出力のサイズとSHA-256を持つ。

`preview` は構図確認専用。灰色のプレースホルダーが含まれるため納品禁止。`demo-assets` と `finalize --allow-demo` は自己試験専用で、公開物には使わない。

