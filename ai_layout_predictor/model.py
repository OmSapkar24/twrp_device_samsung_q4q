"""AI Layout Predictor Module

This module implements machine learning models for predicting optimal UI layouts
for foldable devices based on fold state, user behavior patterns, and app usage.
"""

import torch
import torch.nn as nn
import numpy as np
from typing import Dict, List, Tuple, Optional
import json


class FoldStateEncoder(nn.Module):
    """Encodes device fold state into embeddings."""
    
    def __init__(self, hidden_dim: int = 128):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(8, 64),  # fold angle, screen dims, orientation, etc.
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, hidden_dim),
            nn.ReLU()
        )
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.encoder(x)


class UserBehaviorEncoder(nn.Module):
    """Encodes user behavior patterns and app usage history."""
    
    def __init__(self, vocab_size: int = 1000, embed_dim: int = 64, hidden_dim: int = 128):
        super().__init__()
        self.app_embedding = nn.Embedding(vocab_size, embed_dim)
        self.lstm = nn.LSTM(embed_dim, hidden_dim, batch_first=True, num_layers=2)
        self.attention = nn.MultiheadAttention(hidden_dim, num_heads=4)
    
    def forward(self, app_sequence: torch.Tensor) -> torch.Tensor:
        embedded = self.app_embedding(app_sequence)
        lstm_out, _ = self.lstm(embedded)
        attended, _ = self.attention(lstm_out, lstm_out, lstm_out)
        return attended.mean(dim=1)


class LayoutPredictor(nn.Module):
    """Main model for predicting optimal UI layouts."""
    
    def __init__(self, num_layouts: int = 50, hidden_dim: int = 256):
        super().__init__()
        self.fold_encoder = FoldStateEncoder(hidden_dim // 2)
        self.behavior_encoder = UserBehaviorEncoder(hidden_dim=hidden_dim // 2)
        
        self.fusion = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU()
        )
        
        self.layout_predictor = nn.Sequential(
            nn.Linear(hidden_dim // 2, num_layouts),
            nn.Softmax(dim=-1)
        )
        
        self.confidence_head = nn.Sequential(
            nn.Linear(hidden_dim // 2, 1),
            nn.Sigmoid()
        )
    
    def forward(self, fold_state: torch.Tensor, app_sequence: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        fold_features = self.fold_encoder(fold_state)
        behavior_features = self.behavior_encoder(app_sequence)
        
        combined = torch.cat([fold_features, behavior_features], dim=-1)
        fused = self.fusion(combined)
        
        layout_probs = self.layout_predictor(fused)
        confidence = self.confidence_head(fused)
        
        return layout_probs, confidence


class LayoutOptimizer:
    """Optimizes and applies predicted layouts to foldable device."""
    
    def __init__(self, model_path: Optional[str] = None):
        self.model = LayoutPredictor()
        if model_path:
            self.load_model(model_path)
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model.to(self.device)
        self.model.eval()
    
    def predict_layout(self, fold_state: Dict, app_history: List[str]) -> Dict:
        """Predict optimal layout configuration.
        
        Args:
            fold_state: Current device fold state information
            app_history: Recent app usage history
            
        Returns:
            Dict containing layout configuration and confidence score
        """
        # Encode inputs
        fold_tensor = self._encode_fold_state(fold_state)
        app_tensor = self._encode_app_history(app_history)
        
        with torch.no_grad():
            layout_probs, confidence = self.model(fold_tensor, app_tensor)
        
        # Get top prediction
        best_layout_idx = torch.argmax(layout_probs, dim=-1).item()
        confidence_score = confidence.item()
        
        return {
            'layout_id': best_layout_idx,
            'confidence': confidence_score,
            'layout_config': self._get_layout_config(best_layout_idx),
            'alternatives': self._get_alternative_layouts(layout_probs)
        }
    
    def _encode_fold_state(self, fold_state: Dict) -> torch.Tensor:
        """Convert fold state dict to tensor."""
        features = [
            fold_state.get('angle', 180.0) / 180.0,  # Normalize
            fold_state.get('inner_width', 1768) / 2000.0,
            fold_state.get('inner_height', 2208) / 2500.0,
            fold_state.get('outer_width', 904) / 1000.0,
            fold_state.get('outer_height', 2316) / 2500.0,
            float(fold_state.get('is_unfolded', True)),
            float(fold_state.get('orientation', 0)) / 360.0,
            fold_state.get('screen_brightness', 0.5)
        ]
        return torch.tensor([features], dtype=torch.float32).to(self.device)
    
    def _encode_app_history(self, app_history: List[str]) -> torch.Tensor:
        """Convert app history to tensor indices."""
        # Simplified: map app names to indices
        app_vocab = self._get_app_vocab()
        indices = [app_vocab.get(app, 0) for app in app_history[-20:]]
        # Pad if necessary
        if len(indices) < 20:
            indices += [0] * (20 - len(indices))
        return torch.tensor([indices], dtype=torch.long).to(self.device)
    
    def _get_layout_config(self, layout_id: int) -> Dict:
        """Get detailed layout configuration."""
        # TODO: Load from configuration file
        return {
            'split_mode': 'adaptive',
            'app_continuity': True,
            'flex_mode_enabled': True,
            'multi_window': layout_id > 25
        }
    
    def _get_alternative_layouts(self, probs: torch.Tensor) -> List[Dict]:
        """Get alternative layout suggestions."""
        top_k = torch.topk(probs, k=3, dim=-1)
        alternatives = []
        for idx, prob in zip(top_k.indices[0].tolist(), top_k.values[0].tolist()):
            alternatives.append({
                'layout_id': idx,
                'probability': prob
            })
        return alternatives[1:]  # Exclude top prediction
    
    def _get_app_vocab(self) -> Dict[str, int]:
        """Get app name to index mapping."""
        # TODO: Load from persistent storage
        return {}
    
    def load_model(self, path: str):
        """Load pretrained model weights."""
        self.model.load_state_dict(torch.load(path, map_location=self.device))
    
    def save_model(self, path: str):
        """Save model weights."""
        torch.save(self.model.state_dict(), path)


if __name__ == '__main__':
    # Example usage
    optimizer = LayoutOptimizer()
    
    fold_state = {
        'angle': 180.0,
        'inner_width': 1768,
        'inner_height': 2208,
        'is_unfolded': True,
        'orientation': 0
    }
    
    app_history = ['chrome', 'gmail', 'youtube', 'reddit', 'chrome']
    
    prediction = optimizer.predict_layout(fold_state, app_history)
    print(f"Predicted layout: {prediction}")
