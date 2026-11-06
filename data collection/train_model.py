import torch.nn as nn
from transformers import AutoModel

class ESGModel(nn.Module):
    
    def __init__(self):
        super().__init__()
        self.encoder = AutoModel.from_pretrained("answerdotai/ModernBERT-base")
        hidden = self.encoder.config.hidden_size
        self.dropout = nn.Dropout(0.1)
        self.aspect_head    = nn.Linear(hidden, 3)   # E / S / G
        self.relevance_head = nn.Linear(hidden, 9)   # 0.2 ... 1.0
        self.sentiment_head = nn.Linear(hidden, 3)   # neg / neu / pos

    def forward(self, input_ids, attention_mask):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        m = attention_mask.unsqueeze(-1).float()
        pooled = (out.last_hidden_state * m).sum(1) / m.sum(1).clamp(min=1e-9)
        pooled = self.dropout(pooled)
        return self.aspect_head(pooled), self.relevance_head(pooled), self.sentiment_head(pooled)