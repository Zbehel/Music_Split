# Conversion modèle -> ONNX & quantization (guide)

But: convertir Demucs / modèles PyTorch en ONNX peut être non-trivial selon l'architecture (recurrent/conv, non-tensor argument). Ci-dessous un guide général et options pratiques.

## Pourquoi
- ONNX + onnxruntime sont souvent bien plus rapides sur CPU que PyTorch raw.
- Quantization (FP16/INT8) réduit la taille mémoire et accélère l'inférence CPU.

## Approches possibles

1) Export direct PyTorch -> ONNX
- Charger le modèle Demucs (ou MVSEP) en PyTorch.
- Construire un `dummy_input` de la bonne forme (batch, channels, samples).
- Utiliser `torch.onnx.export(model, dummy_input, "model.onnx", opset_version=13, input_names=[...], output_names=[...])`.
- Tester l'ONNX avec `onnxruntime.InferenceSession("model.onnx")`.

Limitations:
- Certains modèles utilisent des contrôles non-tracé/pythoniques et ne s'exportent pas proprement.
- Demucs internals peuvent nécessiter adaptation.

2) Utiliser `torch.compile`/traces ou exporter des sous-blocs
- Exporter seulement le backbone qui est compatible.
- Laisser la partie pré/post processing en Python.

3) Utiliser `audio-separator` / MVSEP avec ONNX déjà disponible
- Certains backends fournissent des versions ONNX ou onnxruntime optimisées.

## Quantization (après ONNX)
- Utiliser `onnxruntime.quantization` tool (dynamic/static quantization) pour générer INT8-deployment-ready models.
- Exemple:
  ```py
  from onnxruntime.quantization import quantize_dynamic, QuantType
  quantize_dynamic("model.onnx", "model_quant.onnx", weight_type=QuantType.QInt8)
  ```

## Script d'exemple (POC)
- Créer un petit script `scripts/convert_to_onnx.py` qui:
  - charge le modèle,
  - crée dummy input (1, 2, 44100*X),
  - tente `torch.onnx.export` et sauvegarde le .onnx,
  - exécute `onnxruntime.InferenceSession` pour valider.

## Recommandations pratiques
- Faire POC sur un petit modèle / segment court (6s) d'abord.
- Mesurer latence & précision (SNR) entre PyTorch et ONNX outputs.
- Si conversion impossible, considérer un service modèle distinct (GPU) et appeler via RPC/HTTP.

## Dépendances utiles
- `onnx`, `onnxruntime`, `onnxruntime-tools` (quantization)

## Note
- Je peux ajouter un script POC `scripts/convert_to_onnx.py` si vous voulez essayer la conversion automatisée et benchmarker les performances CPU. Dites-moi si vous voulez que je le génère.
