import torch
from torch import nn
import random


class Encoder(nn.Module):
    def __init__(self, vocab_size, dim_embed, dim_hidden, dim_feedforward, num_layers, dropout_probability=0.1):
        super().__init__()

        self.embd_layer = nn.Embedding(vocab_size, dim_embed)
        self.dropout = nn.Dropout(dropout_probability)
        self.rnn = nn.GRU(dim_embed, dim_hidden, num_layers, batch_first=True, dropout=dropout_probability, bidirectional=True)

        self.hidden_map = nn.Sequential(nn.Linear(dim_hidden*2, dim_feedforward),
                                        nn.ReLU(),
                                        nn.Linear(dim_feedforward, dim_hidden),
                                        nn.Dropout(dropout_probability))
        
        self.output_map = nn.Sequential(nn.Linear(dim_hidden*2, dim_feedforward),
                                        nn.ReLU(),
                                        nn.Linear(dim_feedforward, dim_hidden),
                                        nn.Dropout(dropout_probability))

    def forward(self, x):
        embds = self.dropout(self.embd_layer(x))
        context, hidden = self.rnn(embds)
        last_hidden = torch.cat([hidden[-2,:,:], hidden[-1,:,:]], dim=-1)
        to_decoder_hidden = self.hidden_map(last_hidden)
        to_decoder_output = self.output_map(context)
        return to_decoder_output, to_decoder_hidden


class Attention(nn.Module):
    def __init__(self, input_dims):
        super().__init__()

        self.fc_energy = nn.Linear(input_dims*2, input_dims)
        self.alpha = nn.Linear(input_dims, 1, bias=False)

    def forward(self,
                encoder_output, # (B,T,encoder_hidden)
                decoder_hidden): # (B,decoder_hidden)
        ## encoder_hidden = encoder_hidden = input_dims

        seq_len = encoder_output.size(1)
        decoder_hidden = decoder_hidden.unsqueeze(1).repeat(1, seq_len, 1) ## (B,T,input_dims)
        energy = self.fc_energy(torch.cat((decoder_hidden, encoder_output), dim=-1))
        alphas = self.alpha(energy).squeeze(-1)

        return torch.softmax(alphas, dim=-1)




class Decoder(nn.Module):
    def __init__(self, vocab_size, dim_embed, dim_hidden, attention, num_layers, dropout_probability):
        super().__init__()
        self.attention = attention
        self.embd_layer = nn.Embedding(vocab_size, dim_embed)
        self.rnn = nn.GRU(dim_hidden + dim_embed, dim_hidden, batch_first=True, num_layers=num_layers, dropout=dropout_probability)

    def forward(self, x, encoder_output, hidden_t_1):
        ## hidden_t_1 shape: (num_layers,B,dim_hidden)
        ## encoder_output shape : (B,T,dim_hidden)
        ## x shape: (B,1) one token

        embds = self.embd_layer(x) ## (B,1,dim_embed)
        alphas = self.attention(encoder_output, hidden_t_1[-1]).unsqueeze(1) ## (B,1,T)
        attention = torch.bmm(alphas, encoder_output) ## (B,T,dim_embed)
        rnn_input = torch.cat((embds, attention), dim=-1) ## (B,1,dim_hidden + dim_embed)

        output, hidden_t = self.rnn(rnn_input, hidden_t_1)
        
        return output, hidden_t, alphas.squeeze(1) ## "a" is returned for visualization

class Seq2seq_with_attention(nn.Module):
    def __init__(self, encoder_vocab_size:int, decoder_vocab_size:int, dim_embed:int, dim_model:int, dim_feedforward:int, num_layers:int, dropout_probability:float):
        super().__init__()

        self.decoder_vocab_size = decoder_vocab_size
        self.num_layers = num_layers
        self.encoder = Encoder(encoder_vocab_size, dim_embed, dim_model, dim_feedforward, num_layers, dropout_probability)
        self.attention = Attention(dim_model)
        self.decoder = Decoder(decoder_vocab_size, dim_embed, dim_model, self.attention, num_layers, dropout_probability)
        self.classifier = nn.Linear(dim_model, decoder_vocab_size)

    def forward(self, x:torch.tensor, y:torch.tensor, teacher_force_ratio=0.5):
        B, T = y.size()
        total_outputs = torch.zeros(B, T, self.decoder_vocab_size, device=x.device)
        context, hidden = self.encoder(x)
        hidden = hidden.unsqueeze(0).repeat(self.num_layers,1,1) # (numlayer, B, dim_model)
        step_token = y[:, [0]]
        for step in range(1, T):
            out, hidden, alphas = self.decoder(step_token, context, hidden)
            logits = self.classifier(out)
            total_outputs[:, step] = logits.squeeze(1)
            top1 = logits.argmax(-1, keepdim=True)
            x = y[:, [step]] if teacher_force_ratio > random.random() else top1

        return total_outputs
    
    @torch.no_grad
    def translate(self, source:torch.Tensor, sos_tokenId, max_tries=50):
        targets_hat = [sos_tokenId]
        context, hidden = self.encoder(source.unsqueeze(0))
        hidden = hidden.unsqueeze(0).repeat(self.num_layers,1,1) # (numlayer, B, dim_model)
        for step in range(1, max_tries):
            x = torch.tensor([targets_hat[-1]]).unsqueeze(0).to(source.device)
            out, hidden, alphas = self.decoder(x, context, hidden)
            logits = self.classifier(out)
            top1 = logits.argmax(-1)
            targets_hat.append(top1.item())
            if top1 == 3:
                return targets_hat
        return targets_hat
