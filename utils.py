import torch
from torch.utils.data import Dataset
from torch.nn.utils.rnn import pad_sequence
from Tokenizers.Tokenizers import Callable_tokenizer
import matplotlib.pyplot as plt
import os


## Dataset
class MT_Dataset(Dataset):

    def __init__(self, src_sentences_list, trg_sentences_list, src_tokenizer:Callable_tokenizer, trg_tokenizer:Callable_tokenizer, reversed_input=False):
        super(MT_Dataset, self).__init__()

        assert len(src_sentences_list) == len(trg_sentences_list), (f"Lengths mismatched: input has {len(src_sentences_list)} sentences, "f"but target has {len(trg_sentences_list)} sentences.")
        
        self.src_sentences_list = src_sentences_list
        self.trg_sentences_list = trg_sentences_list
        self.src_tokenizer = src_tokenizer
        self.trg_tokenizer = trg_tokenizer
        self.reversed_input = reversed_input
        # self.maxlen = maxlen

    def __len__(self):
        return len(self.src_sentences_list)

    def __getitem__(self, index):
        input, target = self.src_sentences_list[index], self.trg_sentences_list[index]

        input_numrical_tokens = [self.src_tokenizer.get_tokenId('<s>')] + self.src_tokenizer(input) + [self.src_tokenizer.get_tokenId('</s>')]
        target_numrical_tokens = [self.trg_tokenizer.get_tokenId('<s>')] +  self.trg_tokenizer(target) + [self.trg_tokenizer.get_tokenId('</s>')]
        
        input_tensor_tokens = torch.tensor(input_numrical_tokens)
        target_tensor_tokens = torch.tensor(target_numrical_tokens)

        if self.reversed_input: input_tensor_tokens = input_tensor_tokens.flip(0)

        return input_tensor_tokens, target_tensor_tokens
 
    
## Collator
class MYCollate():
    def __init__(self, batch_first=True, pad_value=-100):
        self.pad_value = pad_value
        self.batch_first = batch_first

    def __call__(self, data):
        en_stentences = [ex[0] for ex in data]
        ar_stentences = [ex[1] for ex in data]

        padded_en_stentences = pad_sequence(en_stentences, batch_first=self.batch_first,
                                                      padding_value=self.pad_value)
        padded_ar_stentences = pad_sequence(ar_stentences, batch_first=self.batch_first,
                                                      padding_value=self.pad_value)
        return padded_en_stentences, padded_ar_stentences
    

def get_parameters_info(model):
    names = []
    trainable = []
    nontrainable = []

    for name, module, in model.named_children():
        names.append(name)
        trainable.append(sum(p.numel() for p in module.parameters() if p.requires_grad==True))
        nontrainable.append(sum(p.numel() for p in module.parameters() if p.requires_grad==False))

    names.append("TotalParams")
    trainable.append(sum(trainable))
    nontrainable.append(sum(nontrainable))
    return names, trainable, nontrainable


def plot_loss(train_class_losses, val_class_losses, plots_dir, model_name):

    fig = plt.figure(figsize=(8, 3))
    epochs = [ep + 1 for ep in range(len(train_class_losses))]
    plt.plot(epochs, train_class_losses, label="Training Classification Loss")
    plt.plot(epochs, val_class_losses, label="Validation Classification Loss")
    plt.xlabel("Epochs")
    plt.ylabel("Loss")
    plt.legend()  # Add a legend to differentiate the lines
    plot_path = os.path.join(plots_dir, f'{model_name}_losses.png')
    plt.savefig(plot_path, dpi=300)
    # Close the plot to prevent it from displaying
    plt.close(fig)

def save_checkpoint(model:torch.nn.Module, optimizer, save_dir:str, run_name:str, step:int, in_onnx=False):
    model_path = os.path.join(save_dir, f"{run_name}_step_{step}.pth")
    if in_onnx:
        ## onnx
        print("Converting To ONNX framework...")
    else:
        ## pytorch
        torch.save({'model_state_dict': model.state_dict(),
                    'optimizer_state_dict': optimizer.state_dict()}, model_path)
    print(f"Checkpoint saved at: {model_path}")