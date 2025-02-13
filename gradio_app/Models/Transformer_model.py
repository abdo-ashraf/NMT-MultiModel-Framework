import torch
from torch import nn


class NMT_Transformer(nn.Module):
    def __init__(self, vocab_size:int, dim_embed:int,
                 dim_model:int, dim_feedforward:int, num_layers:int,
                 dropout_probability:float, maxlen:int):
        super().__init__()

        self.embed_shared_src_trg_cls = nn.Embedding(num_embeddings=vocab_size, embedding_dim=dim_embed)
        self.positonal_shared_src_trg = nn.Embedding(num_embeddings=maxlen, embedding_dim=dim_embed)

        # self.trg_embed = nn.Embedding(num_embeddings=vocab_size, embedding_dim=dim_embed)
        # self.trg_pos = nn.Embedding(num_embeddings=maxlen, embedding_dim=dim_embed)

        self.dropout = nn.Dropout(dropout_probability)

        encoder_layer = nn.TransformerEncoderLayer(d_model=dim_model, nhead=8,
                                                   dim_feedforward=dim_feedforward,
                                                   dropout=dropout_probability,
                                                   batch_first=True, norm_first=True)
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers, enable_nested_tensor=False)

        decoder_layer = nn.TransformerDecoderLayer(d_model=dim_model, nhead=8,
                                                   dim_feedforward=dim_feedforward,
                                                   dropout=dropout_probability,
                                                   batch_first=True, norm_first=True)
        self.transformer_decoder = nn.TransformerDecoder(decoder_layer, num_layers=num_layers)
        
        self.classifier = nn.Linear(dim_model, vocab_size)
        ## weight sharing between classifier and embed_shared_src_trg_cls
        self.classifier.weight = self.embed_shared_src_trg_cls.weight

        self.maxlen = maxlen
        self.apply(self._init_weights)

    def _init_weights(self, module):
        if isinstance(module, nn.Linear):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                torch.nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)
        elif isinstance(module, nn.LayerNorm):
            torch.nn.init.ones_(module.weight)
            torch.nn.init.zeros_(module.bias)
    
    def forward(self, source, target, pad_tokenId):
        # target = <sos> + text + <eos>
        # source = text
        B, Ts = source.shape
        B, Tt = target.shape
        device = source.device
        ## Encoder Path
        src_poses = self.positonal_shared_src_trg(torch.arange(0, Ts).to(device).unsqueeze(0).repeat(B, 1))
        src_embedings = self.dropout(self.embed_shared_src_trg_cls(source) + src_poses)

        src_pad_mask = source == pad_tokenId
        memory = self.transformer_encoder(src=src_embedings, mask=None, src_key_padding_mask=src_pad_mask, is_causal=False)
        ## Decoder Path
        trg_poses = self.positonal_shared_src_trg(torch.arange(0, Tt).to(device).unsqueeze(0).repeat(B, 1))
        trg_embedings = self.dropout(self.embed_shared_src_trg_cls(target) + trg_poses)
        
        trg_pad_mask = target == pad_tokenId
        tgt_mask = torch.nn.Transformer.generate_square_subsequent_mask(Tt, dtype=bool).to(device)
        decoder_out = self.transformer_decoder.forward(tgt=trg_embedings,
                                                memory=memory,
                                                tgt_mask=tgt_mask,
                                                memory_mask=None,
                                                tgt_key_padding_mask=trg_pad_mask,
                                                memory_key_padding_mask=None)
        ## Classifier Path
        logits = self.classifier(decoder_out)
        loss = None
        if Tt > 1:
            # for model logits we will need all tokens except the last one
            flat_logits = logits[:,:-1,:].reshape(-1, logits.size(-1))
            # for targets we will need all tokens excapt the first one
            flat_targets = target[:,1:].reshape(-1)
            loss = nn.functional.cross_entropy(flat_logits, flat_targets, ignore_index=pad_tokenId)
        return logits, loss
    

    @torch.no_grad
    def greedy_decode_fast(self, source_tensor:torch.Tensor, sos_tokenId: int, eos_tokenId:int, pad_tokenId, max_tries=50):
        self.eval()
        source_tensor = source_tensor.unsqueeze(0)
        B, Ts = source_tensor.shape
        device = source_tensor.device
        target_tensor = torch.tensor([sos_tokenId]).unsqueeze(0).to(device)

        ## Encoder Path
        src_poses = self.positonal_shared_src_trg(torch.arange(0, Ts).to(device).unsqueeze(0).repeat(B, 1))
        src_embedings = self.embed_shared_src_trg_cls(source_tensor) + src_poses
        src_pad_mask = source_tensor == pad_tokenId
        context = self.transformer_encoder(src=src_embedings, mask=None, src_key_padding_mask=src_pad_mask, is_causal=False)

        for i in range(max_tries):
            ## Decoder Path
            trg_poses = self.positonal_shared_src_trg(torch.arange(0, i+1).to(device).unsqueeze(0).repeat(B, 1))
            trg_embedings = self.embed_shared_src_trg_cls(target_tensor) + trg_poses
            
            trg_pad_mask = target_tensor == pad_tokenId
            tgt_mask = torch.nn.Transformer.generate_square_subsequent_mask(i+1, dtype=bool).to(device)
            decoder_out = self.transformer_decoder.forward(tgt=trg_embedings,
                                                    memory=context,
                                                    tgt_mask=tgt_mask,
                                                    memory_mask=None,
                                                    tgt_key_padding_mask=trg_pad_mask,
                                                    memory_key_padding_mask=None)
            ## Classifier Path
            logits = self.classifier(decoder_out)
            # Greedy decoding
            top1 = logits[:,-1,:].argmax(dim=-1, keepdim=True)
            # Append predicted token
            target_tensor = torch.cat([target_tensor, top1], dim=1)
            
            # Stop if predict <EOS>
            if top1.item() == eos_tokenId:
                break
        return target_tensor.squeeze(0).tolist()