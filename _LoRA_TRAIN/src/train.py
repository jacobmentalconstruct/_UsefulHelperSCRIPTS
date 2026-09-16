# _training/train.py
# QLoRA fine-tuning with Unsloth → merge → GGUF export.
# Tested config for RTX 2070 Super (8GB VRAM) with Mistral 7B.
#
# Prerequisites (run in conda env 'lora_train'):
#   pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
#   pip install --no-deps trl peft accelerate bitsandbytes
#
# Usage:
#   conda activate lora_train
#   python _training/train.py
#
# For a quick smoke-test (10 steps, no full training):
#   python _training/train.py --smoke-test

import argparse
from pathlib import Path

# ─── CONFIG ────────────────────────────────────────────────────────────────────

# Base model — Unsloth hosts pre-quantized 4-bit versions for fast download.
# Swap to "unsloth/phi-3-mini-4k-instruct-bnb-4bit" if you prefer Phi-3.
MODEL_NAME = "unsloth/mistral-7b-instruct-v0.3-bnb-4bit"

# Keep low to fit 8GB VRAM. Reduce to 1024 if you get OOM errors.
MAX_SEQ_LENGTH = 2048

# LoRA rank — higher = more capacity but more VRAM.
# r=16 is a good default for style/persona tuning.
LORA_R = 16
LORA_ALPHA = 16  # Usually set equal to r

# Training data
DATA_FILE = Path(__file__).resolve().parent / "data" / "train.jsonl"

# Where to save the LoRA adapter checkpoint
ADAPTER_DIR = Path(__file__).resolve().parent / "outputs" / "lora_adapter"

# Where to save the final GGUF — drops directly into Mind-Shard's model directory
ROOT_DIR = Path(__file__).resolve().parent.parent
GGUF_OUTPUT_DIR = ROOT_DIR / "models" / "GGUF" / "jacob-mistral-7b"

# Quantization for the exported GGUF.
# q4_k_m: ~4.1GB, best quality/size tradeoff for 7B (recommended)
# q5_k_m: ~4.8GB, slightly better quality
# q8_0:   ~7.2GB, near-lossless (may not fit during inference on 8GB)
QUANT_METHOD = "q4_k_m"

# ─── TRAINING HYPERPARAMETERS ──────────────────────────────────────────────────
# Tuned for 8GB VRAM. batch_size=2 + grad_accum=4 → effective batch of 8.
TRAIN_CONFIG = {
    "per_device_train_batch_size": 2,
    "gradient_accumulation_steps": 4,
    "num_train_epochs": 3,
    "learning_rate": 2e-4,
    "warmup_ratio": 0.03,
    "lr_scheduler_type": "cosine",
    "optim": "adamw_8bit",
    "fp16": True,          # fp16, not bf16 — RTX 2070 Super doesn't support bf16
    "bf16": False,
    "logging_steps": 10,
    "save_steps": 100,
    "output_dir": str(ADAPTER_DIR),
}

# ─── MAIN ──────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="Mind-Shard QLoRA trainer")
    parser.add_argument("--smoke-test", action="store_true",
                        help="Run only 10 steps to verify the pipeline works.")
    parser.add_argument("--model", default=MODEL_NAME,
                        help="Unsloth model repo to fine-tune (default: %(default)s)")
    parser.add_argument("--epochs", type=int, default=3,
                        help="Number of training epochs (default: %(default)s)")
    parser.add_argument("--seq-len", type=int, default=MAX_SEQ_LENGTH,
                        help="Max sequence length — lower to save VRAM (default: %(default)s)")
    parser.add_argument("--quant", default=QUANT_METHOD,
                        choices=["q4_k_m", "q5_k_m", "q8_0"],
                        help="GGUF quantization method (default: %(default)s)")
    parser.add_argument("--lora-r", type=int, default=LORA_R,
                        help="LoRA rank — higher = more capacity, more VRAM (default: %(default)s)")
    return parser.parse_args()


def main():
    args = parse_args()

    if not DATA_FILE.exists():
        print(f"❌ Training data not found at: {DATA_FILE}")
        print("   Run prepare_dataset.py first.")
        return

    # Count training examples
    with open(DATA_FILE, encoding="utf-8") as f:
        n_examples = sum(1 for line in f if line.strip())
    print(f"Training examples: {n_examples}")

    if n_examples < 50 and not args.smoke_test:
        print("⚠️  Very few training examples. Consider adding more data before a full run.")

    # Import here so the script can be inspected without the env installed
    from unsloth import FastLanguageModel
    from trl import SFTTrainer
    from transformers import TrainingArguments
    from datasets import load_dataset

    # Apply CLI overrides
    model_name   = args.model
    max_seq_len  = args.seq_len
    lora_r       = args.lora_r
    quant_method = args.quant
    TRAIN_CONFIG["num_train_epochs"] = args.epochs

    print(f"\nLoading base model: {model_name}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=max_seq_len,
        dtype=None,       # auto-detect
        load_in_4bit=True,
    )

    print("Applying LoRA adapters...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=lora_r,
        lora_alpha=lora_r,  # keep alpha == r
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",  # saves VRAM
        random_state=42,
    )

    print("Loading dataset...")
    dataset = load_dataset("json", data_files=str(DATA_FILE), split="train")

    def format_sharegpt(examples):
        """Convert ShareGPT conversations to the model's chat template."""
        texts = []
        for convs in examples["conversations"]:
            # Remap ShareGPT roles to HF chat format
            messages = []
            for turn in convs:
                role = "user" if turn["from"] == "human" else "assistant"
                messages.append({"role": role, "content": turn["value"]})
            text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=False,
            )
            texts.append(text)
        return {"text": texts}

    dataset = dataset.map(format_sharegpt, batched=True, remove_columns=dataset.column_names)

    train_config = dict(TRAIN_CONFIG)
    if args.smoke_test:
        train_config["max_steps"] = 10
        train_config["num_train_epochs"] = 1
        print("\n🔬 Smoke-test mode: running 10 steps only.")

    ADAPTER_DIR.mkdir(parents=True, exist_ok=True)

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=max_seq_len,
        dataset_num_proc=2,
        args=TrainingArguments(**train_config),
    )

    print("\nStarting training...")
    print("Watch VRAM with: nvidia-smi dmon -s u")
    trainer.train()

    print(f"\n✅ Training complete. Adapter saved to: {ADAPTER_DIR}")

    if args.smoke_test:
        print("Smoke-test done. Re-run without --smoke-test for full training.")
        return

    # ─── GGUF Export ───────────────────────────────────────────────────────────
    print(f"\nExporting to GGUF ({quant_method})...")
    print(f"Output: {GGUF_OUTPUT_DIR}")
    GGUF_OUTPUT_DIR.parent.mkdir(parents=True, exist_ok=True)

    model.save_pretrained_gguf(
        str(GGUF_OUTPUT_DIR),
        tokenizer,
        quantization_method=quant_method,
    )

    # Unsloth appends quantization info to the filename, find what it created
    gguf_files = list(GGUF_OUTPUT_DIR.parent.glob("jacob-mistral-7b*.gguf"))
    if gguf_files:
        gguf_path = gguf_files[0]
        size_gb = gguf_path.stat().st_size / 1e9
        print(f"\n✅ GGUF saved: {gguf_path.name} ({size_gb:.1f} GB)")
        print("   Load it in Mind-Shard by selecting it from models/GGUF/")
    else:
        print(f"\n✅ GGUF export complete. Check: {GGUF_OUTPUT_DIR.parent}")


if __name__ == "__main__":
    main()
