
import math
from functools import partial

import torch
import torch.nn as nn

from utils import trunc_normal_
from ours_vit import to_2tuple


def drop_path(x, drop_prob: float = 0., training: bool = False):
    if drop_prob == 0. or not training:
        return x
    keep_prob = 1 - drop_prob
    shape = (x.shape[0],) + (1,) * (x.ndim - 1)  # work with diff dim tensors, not just 2D ConvNets
    random_tensor = keep_prob + torch.rand(shape, dtype=x.dtype, device=x.device)
    random_tensor.floor_()  # binarize
    output = x.div(keep_prob) * random_tensor
    return output


class DropPath(nn.Module):
    """Drop paths (Stochastic Depth) per sample  (when applied in main path of residual blocks).
    """
    def __init__(self, drop_prob=None):
        super(DropPath, self).__init__()
        self.drop_prob = drop_prob

    def forward(self, x):
        return drop_path(x, self.drop_prob, self.training)


class Mlp(nn.Module):
    def __init__(self, in_features, hidden_features=None, out_features=None, act_layer=nn.GELU, drop=0.):
        super().__init__()
        out_features = out_features or in_features
        hidden_features = hidden_features or in_features
        self.fc1 = nn.Linear(in_features, hidden_features)
        self.act = act_layer()
        self.fc2 = nn.Linear(hidden_features, out_features)
        self.drop = nn.Dropout(drop)

    def forward(self, x):
        x = self.fc1(x)
        x = self.act(x)
        x = self.drop(x)
        x = self.fc2(x)
        x = self.drop(x)
        return x


class Attention(nn.Module):
    def __init__(self, dim, num_heads=8, qkv_bias=False, qk_scale=None, attn_drop=0., proj_drop=0.):
        super().__init__()
        self.num_heads = num_heads
        head_dim = dim // num_heads
        self.scale = qk_scale or head_dim ** -0.5

        self.qkv = nn.Linear(dim, dim * 3, bias=qkv_bias)
        self.attn_drop = nn.Dropout(attn_drop)
        self.proj = nn.Linear(dim, dim)
        self.proj_drop = nn.Dropout(proj_drop)

    def forward(self, x):
        B, N, C = x.shape
        qkv = self.qkv(x).reshape(B, N, 3, self.num_heads, C // self.num_heads).permute(2, 0, 3, 1, 4)
        q, k, v = qkv[0], qkv[1], qkv[2]

        attn = (q @ k.transpose(-2, -1)) * self.scale
        attn = attn.softmax(dim=-1)
        attn = self.attn_drop(attn)

        x = (attn @ v).transpose(1, 2).reshape(B, N, C)
        x = self.proj(x)
        x = self.proj_drop(x)
        return x, attn


class Block(nn.Module):
    def __init__(self, dim, num_heads, mlp_ratio=4., qkv_bias=False, qk_scale=None, drop=0., attn_drop=0.,
                 drop_path=0., act_layer=nn.GELU, norm_layer=nn.LayerNorm):
        super().__init__()
        self.norm1 = norm_layer(dim)
        self.attn = Attention(
            dim, num_heads=num_heads, qkv_bias=qkv_bias, qk_scale=qk_scale, attn_drop=attn_drop, proj_drop=drop)
        self.drop_path = DropPath(drop_path) if drop_path > 0. else nn.Identity()
        self.norm2 = norm_layer(dim)
        mlp_hidden_dim = int(dim * mlp_ratio)
        self.mlp = Mlp(in_features=dim, hidden_features=mlp_hidden_dim, act_layer=act_layer, drop=drop)

    def forward(self, x, return_attention=False):
        y, attn = self.attn(self.norm1(x))
        if return_attention:
            return attn
        x = x + self.drop_path(y)
        x = x + self.drop_path(self.mlp(self.norm2(x)))
        return x


class PatchEmbed(nn.Module):
    """ Image to Patch Embedding
    """
    def __init__(self, img_size=224, patch_size=16, in_chans=3, embed_dim=768):
        super().__init__()
        num_patches = (img_size[0] // patch_size) * (img_size[1] // patch_size)
        self.img_size = img_size
        self.patch_size = patch_size
        self.num_patches = num_patches

        self.proj = nn.Conv2d(in_chans, embed_dim, kernel_size=patch_size, stride=patch_size)

    def forward(self, x):
        B, C, H, W = x.shape
        x = self.proj(x).flatten(2).transpose(1, 2)
        return x


class VisionTransformer(nn.Module):
    """ Vision Transformer """
    def __init__(self, img_size=(224,224), patch_size=16, in_chans=3, num_classes=0, embed_dim=768, depth=12,
                 num_heads=12, mlp_ratio=4., qkv_bias=False, qk_scale=None, drop_rate=0., attn_drop_rate=0.,
                 drop_path_rate=0., norm_layer=nn.LayerNorm, **kwargs):
        super().__init__()
        self.num_features = self.embed_dim = embed_dim

        self.img_size = to_2tuple(img_size)
        self.patch_embed = PatchEmbed(
            img_size=self.img_size, patch_size=patch_size, in_chans=in_chans, embed_dim=embed_dim)
        num_patches = self.patch_embed.num_patches

        self.cls_token = nn.Parameter(torch.zeros(1, 1, embed_dim))
        self.part_token1 = nn.Parameter(torch.zeros(1, 1, embed_dim))
        self.part_token2 = nn.Parameter(torch.zeros(1, 1, embed_dim))
        self.part_token3 = nn.Parameter(torch.zeros(1, 1, embed_dim))
        
        self.cls_pos = nn.Parameter(torch.zeros(1, 1, embed_dim))
        self.part1_pos = nn.Parameter(torch.zeros(1, 1, embed_dim))
        self.part2_pos = nn.Parameter(torch.zeros(1, 1, embed_dim))
        self.part3_pos = nn.Parameter(torch.zeros(1, 1, embed_dim))
        self.pos_embed = nn.Parameter(torch.zeros(1, num_patches, embed_dim))
        self.pos_drop = nn.Dropout(p=drop_rate)

        dpr = [x.item() for x in torch.linspace(0, drop_path_rate, depth)]  # stochastic depth decay rule
        self.blocks = nn.ModuleList([
            Block(
                dim=embed_dim, num_heads=num_heads, mlp_ratio=mlp_ratio, qkv_bias=qkv_bias, qk_scale=qk_scale,
                drop=drop_rate, attn_drop=attn_drop_rate, drop_path=dpr[i], norm_layer=norm_layer)
            for i in range(depth)])
        self.norm = norm_layer(embed_dim)

        # Classifier head
        self.head = nn.Linear(embed_dim, num_classes) if num_classes > 0 else nn.Identity()

        trunc_normal_(self.pos_embed, std=.02)
        trunc_normal_(self.part1_pos, std=.02)
        trunc_normal_(self.part2_pos, std=.02)
        trunc_normal_(self.part3_pos, std=.02)
        trunc_normal_(self.cls_token, std=.02)
        trunc_normal_(self.part_token1, std=.02)
        trunc_normal_(self.part_token2, std=.02)
        trunc_normal_(self.part_token3, std=.02)
        self.apply(self._init_weights)

    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            trunc_normal_(m.weight, std=.02)
            if isinstance(m, nn.Linear) and m.bias is not None:
                nn.init.constant_(m.bias, 0)
        elif isinstance(m, nn.LayerNorm):
            nn.init.constant_(m.bias, 0)
            nn.init.constant_(m.weight, 1.0)

    #  def interpolate_pos_encoding(self, x, w, h):
        #  npatch = x.shape[1] - 1
        #  N = self.pos_embed.shape[1] - 1
        #  if npatch == N and w == h:
            #  return self.pos_embed
        #  class_pos_embed = self.pos_embed[:, 0]
        #  patch_pos_embed = self.pos_embed[:, 1:]
        #  dim = x.shape[-1]
        #  w0 = w // self.patch_embed.patch_size
        #  h0 = h // self.patch_embed.patch_size
        #  # we add a small number to avoid floating point error in the interpolation
        #  # see discussion at https://github.com/facebookresearch/dino/issues/8
        #  w0, h0 = w0 + 0.1, h0 + 0.1
        #  from IPython import embed
        #  embed()
        #  patch_pos_embed = nn.functional.interpolate(
            #  patch_pos_embed.reshape(1, int(math.sqrt(N)), int(math.sqrt(N)), dim).permute(0, 3, 1, 2),
            #  scale_factor=(w0 / math.sqrt(N), h0 / math.sqrt(N)),
            #  mode='bicubic',
        #  )
        #  assert int(w0) == patch_pos_embed.shape[-2] and int(h0) == patch_pos_embed.shape[-1]
        #  patch_pos_embed = patch_pos_embed.permute(0, 2, 3, 1).view(1, -1, dim)
        #  return torch.cat((class_pos_embed.unsqueeze(0), patch_pos_embed), dim=1)

    def interpolate_pos_encoding(self, npatch, dim, h, w):
        N = self.pos_embed.shape[1]
        if npatch == N and self.img_size == (h,w):
            return self.pos_embed
        
        patch_pos_embed = self.pos_embed
        OH = self.img_size[0] // self.patch_embed.patch_size
        OW = self.img_size[1] // self.patch_embed.patch_size
        w0 = w // self.patch_embed.patch_size
        h0 = h // self.patch_embed.patch_size
        # we add a small number to avoid floating point error in the interpolation
        # see discussion at https://github.com/facebookresearch/dino/issues/8
        w0, h0 = w0 + 0.1, h0 + 0.1
        patch_pos_embed = nn.functional.interpolate(
            patch_pos_embed.reshape(1, OH, OW, dim).permute(0, 3, 1, 2),
            scale_factor=(h0 / OH, w0 / OW),
            mode='bicubic',
        )
        assert int(w0) == patch_pos_embed.shape[-1] and int(h0) == patch_pos_embed.shape[-2]
        patch_pos_embed = patch_pos_embed.permute(0, 2, 3, 1).view(1, -1, dim)
        return patch_pos_embed

    def prepare_tokens(self, x, part_index):
        B, nc, w, h = x.shape
        x = self.patch_embed(x)  # patch linear embedding

        # add the [CLS] token to the embed patch tokens
        if part_index == None:
            cls_tokens = self.cls_token.expand(B, -1, -1)
            part_tokens1 = self.part_token1.expand(B, -1, -1)
            part_tokens2 = self.part_token2.expand(B, -1, -1)
            part_tokens3 = self.part_token3.expand(B, -1, -1)
            x = torch.cat((cls_tokens, part_tokens1, part_tokens2, part_tokens3, x), dim=1)
    
            # add positional encoding to each token
            x = x + torch.cat((self.cls_pos, self.part1_pos, self.part2_pos, self.part3_pos, self.interpolate_pos_encoding(x.shape[1], x.shape[-1], w, h)), dim=1)
        else:
            if part_index==0:
                cls_tokens = self.cls_token.expand(B, -1, -1)
                part_tokens1 = self.part_token1.expand(B, -1, -1)
                x = torch.cat((cls_tokens, part_tokens1, x), dim=1)
        
                # add positional encoding to each token
                x = x + torch.cat((self.cls_pos, self.part1_pos, self.interpolate_pos_encoding(x.shape[1], x.shape[-1], w, h)), dim=1)
            elif part_index==1:
                cls_tokens = self.cls_token.expand(B, -1, -1)
                part_tokens2 = self.part_token2.expand(B, -1, -1)
                x = torch.cat((cls_tokens, part_tokens2, x), dim=1)
        
                # add positional encoding to each token
                x = x + torch.cat((self.cls_pos, self.part2_pos, self.interpolate_pos_encoding(x.shape[1], x.shape[-1], w, h)), dim=1)
            elif part_index==2:
                cls_tokens = self.cls_token.expand(B, -1, -1)
                part_tokens3 = self.part_token3.expand(B, -1, -1)
                x = torch.cat((cls_tokens, part_tokens3, x), dim=1)
        
                # add positional encoding to each token
                x = x + torch.cat((self.cls_pos, self.part3_pos, self.interpolate_pos_encoding(x.shape[1], x.shape[-1], w, h)), dim=1)

        return self.pos_drop(x)

    def forward(self, x, part_index):
        x = self.prepare_tokens(x, part_index)
        for blk in self.blocks:
            x = blk(x)
        x = self.norm(x)
        if part_index==None:
            return x[:, 0], x[:, 1], x[:, 2], x[:, 3]
        else:
            return x[:, 0], x[:, 1]
                

    def get_last_selfattention(self, x):
        x = self.prepare_tokens(x, None)
        for i, blk in enumerate(self.blocks):
            if i < len(self.blocks) - 1:
                x = blk(x)
            else:
                # return attention of the last block
                return blk(x, return_attention=True)
    

    def get_intermediate_layers(self, x, n=1):
        x = self.prepare_tokens(x)
        # we return the output tokens from the `n` last blocks
        output = []
        for i, blk in enumerate(self.blocks):
            x = blk(x)
            if len(self.blocks) - i <= n:
                output.append(self.norm(x))
        return output


def vit_tiny(patch_size=16, **kwargs):
    model = VisionTransformer(
        patch_size=patch_size, embed_dim=192, depth=12, num_heads=3, mlp_ratio=4,
        qkv_bias=True, norm_layer=partial(nn.LayerNorm, eps=1e-6), **kwargs)
    return model


def vit_small(patch_size=16, **kwargs):
    model = VisionTransformer(
        patch_size=patch_size, embed_dim=384, depth=12, num_heads=6, mlp_ratio=4,
        qkv_bias=True, norm_layer=partial(nn.LayerNorm, eps=1e-6), **kwargs)
    return model


def vit_base(patch_size=16, **kwargs):
    model = VisionTransformer(
        patch_size=patch_size, embed_dim=768, depth=12, num_heads=12, mlp_ratio=4,
        qkv_bias=True, norm_layer=partial(nn.LayerNorm, eps=1e-6), **kwargs)
    return model


class DINOHead(nn.Module):
    def __init__(self, in_dim, out_dim, use_bn=False, norm_last_layer=True, nlayers=3, hidden_dim=2048, bottleneck_dim=256):
        super().__init__()
        nlayers = max(nlayers, 1)
        if nlayers == 1:
            self.mlp = nn.Linear(in_dim, bottleneck_dim)
        else:
            layers = [nn.Linear(in_dim, hidden_dim)]
            if use_bn:
                layers.append(nn.BatchNorm1d(hidden_dim))
            layers.append(nn.GELU())
            for _ in range(nlayers - 2):
                layers.append(nn.Linear(hidden_dim, hidden_dim))
                if use_bn:
                    layers.append(nn.BatchNorm1d(hidden_dim))
                layers.append(nn.GELU())
            layers.append(nn.Linear(hidden_dim, bottleneck_dim))
            self.mlp_cls = nn.Sequential(*layers)
            
            layers = [nn.Linear(in_dim, hidden_dim)]
            if use_bn:
                layers.append(nn.BatchNorm1d(hidden_dim))
            layers.append(nn.GELU())
            for _ in range(nlayers - 2):
                layers.append(nn.Linear(hidden_dim, hidden_dim))
                if use_bn:
                    layers.append(nn.BatchNorm1d(hidden_dim))
                layers.append(nn.GELU())
            layers.append(nn.Linear(hidden_dim, bottleneck_dim))
            self.mlp_pt1 = nn.Sequential(*layers)
            
            layers = [nn.Linear(in_dim, hidden_dim)]
            if use_bn:
                layers.append(nn.BatchNorm1d(hidden_dim))
            layers.append(nn.GELU())
            for _ in range(nlayers - 2):
                layers.append(nn.Linear(hidden_dim, hidden_dim))
                if use_bn:
                    layers.append(nn.BatchNorm1d(hidden_dim))
                layers.append(nn.GELU())
            layers.append(nn.Linear(hidden_dim, bottleneck_dim))
            self.mlp_pt2 = nn.Sequential(*layers)
            
            layers = [nn.Linear(in_dim, hidden_dim)]
            if use_bn:
                layers.append(nn.BatchNorm1d(hidden_dim))
            layers.append(nn.GELU())
            for _ in range(nlayers - 2):
                layers.append(nn.Linear(hidden_dim, hidden_dim))
                if use_bn:
                    layers.append(nn.BatchNorm1d(hidden_dim))
                layers.append(nn.GELU())
            layers.append(nn.Linear(hidden_dim, bottleneck_dim))
            self.mlp_pt3 = nn.Sequential(*layers)
            
        self.apply(self._init_weights)
        
        self.last_layer_cls = nn.utils.weight_norm(nn.Linear(bottleneck_dim, out_dim, bias=False))
        self.last_layer_cls.weight_g.data.fill_(1)
        
        self.last_layer_pt1 = nn.utils.weight_norm(nn.Linear(bottleneck_dim, out_dim, bias=False))
        self.last_layer_pt1.weight_g.data.fill_(1)
        
        self.last_layer_pt2 = nn.utils.weight_norm(nn.Linear(bottleneck_dim, out_dim, bias=False))
        self.last_layer_pt2.weight_g.data.fill_(1)
        
        self.last_layer_pt3 = nn.utils.weight_norm(nn.Linear(bottleneck_dim, out_dim, bias=False))
        self.last_layer_pt3.weight_g.data.fill_(1)
        
        if norm_last_layer:
            self.last_layer_cls.weight_g.requires_grad = False
            self.last_layer_pt1.weight_g.requires_grad = False
            self.last_layer_pt2.weight_g.requires_grad = False
            self.last_layer_pt3.weight_g.requires_grad = False

    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            trunc_normal_(m.weight, std=.02)
            if isinstance(m, nn.Linear) and m.bias is not None:
                nn.init.constant_(m.bias, 0)

    def forward(self, x, part_index):
        if part_index==None:
            cls = self.mlp_cls(x[0])
            cls = nn.functional.normalize(cls, dim=-1, p=2)
            cls = self.last_layer_cls(cls)
            
            pt1 = self.mlp_pt1(x[1])
            pt1 = nn.functional.normalize(pt1, dim=-1, p=2)
            pt1 = self.last_layer_pt1(pt1)
            
            pt2 = self.mlp_pt2(x[2])
            pt2 = nn.functional.normalize(pt2, dim=-1, p=2)
            pt2 = self.last_layer_pt2(pt2)
            
            pt3 = self.mlp_pt3(x[3])
            pt3 = nn.functional.normalize(pt3, dim=-1, p=2)
            pt3 = self.last_layer_pt3(pt3)
            
            return cls, pt1, pt2, pt3
        
        else:
            
            cls = self.mlp_cls(x[0])
            cls = nn.functional.normalize(cls, dim=-1, p=2)
            cls = self.last_layer_cls(cls)
            
            if part_index==0:
                pt1 = self.mlp_pt1(x[1])
                pt1 = nn.functional.normalize(pt1, dim=-1, p=2)
                pt1 = self.last_layer_pt1(pt1)
                return cls, pt1
            elif part_index==1:
                pt2 = self.mlp_pt2(x[1])
                pt2 = nn.functional.normalize(pt2, dim=-1, p=2)
                pt2 = self.last_layer_pt2(pt2)
                return cls, pt2
            elif part_index==2:
                pt3 = self.mlp_pt3(x[1])
                pt3 = nn.functional.normalize(pt3, dim=-1, p=2)
                pt3 = self.last_layer_pt3(pt3)
                return cls, pt3
            
        
        
        
        
