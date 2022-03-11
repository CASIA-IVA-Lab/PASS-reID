
import argparse
import os
import sys
import datetime
import time
import math
import json
from pathlib import Path
import pickle

import numpy as np
from PIL import Image
import torch
import torch.nn as nn
import torch.distributed as dist
import torch.backends.cudnn as cudnn
import torch.nn.functional as F
from torchvision import datasets, transforms
from torchvision import models as torchvision_models

import utils
import vision_transformer as vits
from vision_transformer import DINOHead
from ours_vit import ours_vit_small, ours_vit_base

torchvision_archs = sorted(name for name in torchvision_models.__dict__
    if name.islower() and not name.startswith("__")
    and callable(torchvision_models.__dict__[name]))

def get_args_parser():
    parser = argparse.ArgumentParser('DINO', add_help=False)

    # Model parameters
    parser.add_argument('--arch', default='vit_small', type=str,
        #  choices=['vit_tiny', 'vit_small', 'vit_base', 'deit_tiny', 'deit_small'] + torchvision_archs,
        help="""Name of architecture to train. For quick experiments with ViTs,
        we recommend using vit_tiny or vit_small.""")
    parser.add_argument('--patch_size', default=16, type=int, help="""Size in pixels
        of input square patches - default 16 (for 16x16 patches). Using smaller
        values leads to better performance but requires more memory. Applies only
        for ViTs (vit_tiny, vit_small and vit_base). If <16, we recommend disabling
        mixed precision training (--use_fp16 false) to avoid unstabilities.""")
    parser.add_argument('--height', default=224, type=int, help="""Height of image""")
    parser.add_argument('--width', default=224, type=int, help="""Width of image""")
    parser.add_argument('--crop_height', default=96, type=int, help="""Height of crop image""")
    parser.add_argument('--crop_width', default=96, type=int, help="""Width of crop image""")
    parser.add_argument('--out_dim', default=65536, type=int, help="""Dimensionality of
        the DINO head output. For complex and large datasets large values (like 65k) work well.""")
    parser.add_argument('--norm_last_layer', default=True, type=utils.bool_flag,
        help="""Whether or not to weight normalize the last layer of the DINO head.
        Not normalizing leads to better performance but can make the training unstable.
        In our experiments, we typically set this paramater to False with vit_small and True with vit_base.""")
    parser.add_argument('--momentum_teacher', default=0.996, type=float, help="""Base EMA
        parameter for teacher update. The value is increased to 1 during training with cosine schedule.
        We recommend setting a higher value with small batches: for example use 0.9995 with batch size of 256.""")
    parser.add_argument('--use_bn_in_head', default=False, type=utils.bool_flag,
        help="Whether to use batch normalizations in projection head (Default: False)")

    # Temperature teacher parameters
    parser.add_argument('--warmup_teacher_temp', default=0.04, type=float,
        help="""Initial value for the teacher temperature: 0.04 works well in most cases.
        Try decreasing it if the training loss does not decrease.""")
    parser.add_argument('--teacher_temp', default=0.04, type=float, help="""Final value (after linear warmup)
        of the teacher temperature. For most experiments, anything above 0.07 is unstable. We recommend
        starting with the default value of 0.04 and increase this slightly if needed.""")
    parser.add_argument('--warmup_teacher_temp_epochs', default=0, type=int,
        help='Number of warmup epochs for the teacher temperature (Default: 30).')

    # Training/Optimization parameters
    parser.add_argument('--use_fp16', type=utils.bool_flag, default=True, help="""Whether or not
        to use half precision for training. Improves training time and memory requirements,
        but can provoke instability and slight decay of performance. We recommend disabling
        mixed precision if the loss is unstable, if reducing the patch size or if training with bigger ViTs.""")
    parser.add_argument('--weight_decay', type=float, default=0.04, help="""Initial value of the
        weight decay. With ViT, a smaller value at the beginning of training works well.""")
    parser.add_argument('--weight_decay_end', type=float, default=0.4, help="""Final value of the
        weight decay. We use a cosine schedule for WD and using a larger decay by
        the end of training improves performance for ViTs.""")
    parser.add_argument('--clip_grad', type=float, default=3.0, help="""Maximal parameter
        gradient norm if using gradient clipping. Clipping with norm .3 ~ 1.0 can
        help optimization for larger ViT architectures. 0 for disabling.""")
    parser.add_argument('--batch_size_per_gpu', default=64, type=int,
        help='Per-GPU batch-size : number of distinct images loaded on one GPU.')
    parser.add_argument('--epochs', default=100, type=int, help='Number of epochs of training.')
    parser.add_argument('--freeze_last_layer', default=1, type=int, help="""Number of epochs
        during which we keep the output layer fixed. Typically doing so during
        the first epoch helps training. Try increasing this value if the loss does not decrease.""")
    parser.add_argument("--lr", default=0.0005, type=float, help="""Learning rate at the end of
        linear warmup (highest LR used during training). The learning rate is linearly scaled
        with the batch size, and specified here for a reference batch size of 256.""")
    parser.add_argument("--warmup_epochs", default=10, type=int,
        help="Number of epochs for the linear learning-rate warm up.")
    parser.add_argument('--min_lr', type=float, default=1e-6, help="""Target LR at the
        end of optimization. We use a cosine LR schedule with linear warmup.""")
    parser.add_argument('--optimizer', default='adamw', type=str,
        choices=['adamw', 'sgd', 'lars'], help="""Type of optimizer. We recommend using adamw with ViTs.""")

    # Multi-crop parameters
    parser.add_argument('--global_crops_scale', type=float, nargs='+', default=(0.4, 1.),
        help="""Scale range of the cropped image before resizing, relatively to the origin image.
        Used for large global view cropping. When disabling multi-crop (--local_crops_number 0), we
        recommand using a wider range of scale ("--global_crops_scale 0.14 1." for example)""")
    parser.add_argument('--local_crops_number', type=int, default=8, help="""Number of small
        local views to generate. Set this parameter to 0 to disable multi-crop training.
        When disabling multi-crop we recommend to use "--global_crops_scale 0.14 1." """)
    parser.add_argument('--local_crops_scale', type=float, nargs='+', default=(0.05, 0.4),
        help="""Scale range of the cropped image before resizing, relatively to the origin image.
        Used for small local view cropping of multi-crop.""")

    # Misc
    parser.add_argument('--data_path', default='/path/to/imagenet/train/', type=str,
        help='Please specify path to the ImageNet training data.')
    parser.add_argument('--filter_path', default='', type=str, help='Filter of image list.')
    parser.add_argument('--keep_num', default=1281167, type=int, help='Number of training images.')
    parser.add_argument('--output_dir', default=".", type=str, help='Path to save logs and checkpoints.')
    parser.add_argument('--saveckp_freq', default=5, type=int, help='Save checkpoint every x epochs.')
    parser.add_argument('--seed', default=0, type=int, help='Random seed.')
    parser.add_argument('--num_workers', default=16, type=int, help='Number of data loading workers per GPU.')
    parser.add_argument("--dist_url", default="env://", type=str, help="""url used to set up
        distributed training; see https://pytorch.org/docs/stable/distributed.html""")
    parser.add_argument("--local_rank", default=0, type=int, help="Please ignore and do not set this argument.")
    return parser


def train_dino(args):
    utils.init_distributed_mode(args)
    utils.fix_random_seeds(args.seed)
    print("git:\n  {}\n".format(utils.get_sha()))
    print("\n".join("%s: %s" % (k, str(v)) for k, v in sorted(dict(vars(args)).items())))
    cudnn.benchmark = True

    # ============ preparing data ... ============
    transform = DataAugmentationDINO(
        (args.height,args.width),
        (args.crop_height,args.crop_width),
        args.global_crops_scale,
        args.local_crops_scale,
        args.local_crops_number,
    )
    dataset = datasets.ImageFolder(args.data_path, transform=transform)
    if args.filter_path != '':
        save_list = pickle.load(open(args.filter_path, "rb"))
        keep_num = args.keep_num
        label = [0 for i in range(keep_num)]
        dir_path = os.path.join(args.data_path,'images')
        used_list = [os.path.join(dir_path,i) for i in save_list[:keep_num]]
        dataset.samples = list(zip(used_list,label))
        dataset.imgs = dataset.samples
    sampler = torch.utils.data.DistributedSampler(dataset, shuffle=True)
    data_loader = torch.utils.data.DataLoader(
        dataset,
        sampler=sampler,
        batch_size=args.batch_size_per_gpu,
        num_workers=args.num_workers,
        pin_memory=True,
        drop_last=True,
    )
    print(f"Data loaded: there are {len(dataset)} images.")

    # ============ building student and teacher networks ... ============
    # we changed the name DeiT-S for ViT-S to avoid confusions
    args.arch = args.arch.replace("deit", "vit")
    # if the network is a vision transformer (i.e. vit_tiny, vit_small, vit_base)
    if args.arch in vits.__dict__.keys():
        student = vits.__dict__[args.arch](
            img_size=(args.height, args.width),
            patch_size=args.patch_size,
            drop_path_rate=0.1,  # stochastic depth
        )
        teacher = vits.__dict__[args.arch](
                img_size= (args.height,args.width),
                patch_size=args.patch_size)
        embed_dim = student.embed_dim
    # otherwise, we check if the architecture is in torchvision models
    elif args.arch in torchvision_models.__dict__.keys():
        student = torchvision_models.__dict__[args.arch]()
        teacher = torchvision_models.__dict__[args.arch]()
        embed_dim = student.fc.weight.shape[1]
    elif args.arch == 'ours_vit_small':
        student = ours_vit_small(
            img_size=(args.height, args.width),
            patch_size=args.patch_size,
            drop_path_rate=0.1,  # stochastic depth
        )
        teacher = ours_vit_small(
                img_size= (args.height,args.width),
                patch_size=args.patch_size)
        embed_dim = student.embed_dim
    elif args.arch == 'ours_vit_base':
        student = ours_vit_base(
            img_size=(args.height, args.width),
            patch_size=args.patch_size,
            drop_path_rate=0.1,  # stochastic depth
        )
        teacher = ours_vit_base(
                img_size= (args.height,args.width),
                patch_size=args.patch_size)
        embed_dim = student.embed_dim
    else:
        print(f"Unknow architecture: {args.arch}")

    # multi-crop wrapper handles forward with inputs of different resolutions
    student = utils.MultiCropWrapper(student, DINOHead(
        embed_dim,
        args.out_dim,
        use_bn=args.use_bn_in_head,
        norm_last_layer=args.norm_last_layer,
    ))
    teacher = utils.MultiCropWrapper(
        teacher,
        DINOHead(embed_dim, args.out_dim, args.use_bn_in_head),
    )
    # move networks to gpu
    student, teacher = student.cuda(), teacher.cuda()
    # synchronize batch norms (if any)
    if utils.has_batchnorms(student):
        student = nn.SyncBatchNorm.convert_sync_batchnorm(student)
        teacher = nn.SyncBatchNorm.convert_sync_batchnorm(teacher)

        # we need DDP wrapper to have synchro batch norms working...
        teacher = nn.parallel.DistributedDataParallel(teacher, device_ids=[args.gpu])
        teacher_without_ddp = teacher.module
    else:
        # teacher_without_ddp and teacher are the same thing
        teacher_without_ddp = teacher
    student = nn.parallel.DistributedDataParallel(student, device_ids=[args.gpu])
    # teacher and student start with the same weights
    teacher_without_ddp.load_state_dict(student.module.state_dict())
    # there is no backpropagation through the teacher, so no need for gradients
    for p in teacher.parameters():
        p.requires_grad = False
    print(f"Student and Teacher are built: they are both {args.arch} network.")

    # ============ preparing loss ... ============
    dino_loss = DINOLoss(
        args.out_dim,
        args.local_crops_number + 2,  # total number of crops = 2 global crops + local_crops_number
        args.warmup_teacher_temp,
        args.teacher_temp,
        args.warmup_teacher_temp_epochs,
        args.epochs,
    ).cuda()

    # ============ preparing optimizer ... ============
    params_groups = utils.get_params_groups(student)
    if args.optimizer == "adamw":
        optimizer = torch.optim.AdamW(params_groups)  # to use with ViTs
    elif args.optimizer == "sgd":
        optimizer = torch.optim.SGD(params_groups, lr=0, momentum=0.9)  # lr is set by scheduler
    elif args.optimizer == "lars":
        optimizer = utils.LARS(params_groups)  # to use with convnet and large batches
    # for mixed precision training
    fp16_scaler = None
    if args.use_fp16:
        fp16_scaler = torch.cuda.amp.GradScaler()

    # ============ init schedulers ... ============
    lr_schedule = utils.cosine_scheduler(
        args.lr * (args.batch_size_per_gpu * utils.get_world_size()) / 256.,  # linear scaling rule
        args.min_lr,
        args.epochs, len(data_loader),
        warmup_epochs=args.warmup_epochs,
    )
    wd_schedule = utils.cosine_scheduler(
        args.weight_decay,
        args.weight_decay_end,
        args.epochs, len(data_loader),
    )
    # momentum parameter is increased to 1. during training with a cosine schedule
    momentum_schedule = utils.cosine_scheduler(args.momentum_teacher, 1,
                                               args.epochs, len(data_loader))
    print(f"Loss, optimizer and schedulers ready.")

    # ============ optionally resume training ... ============
    to_restore = {"epoch": 0}
    utils.restart_from_checkpoint(
        os.path.join(args.output_dir, "checkpoint.pth"),
        run_variables=to_restore,
        student=student,
        teacher=teacher,
        optimizer=optimizer,
        fp16_scaler=fp16_scaler,
        dino_loss=dino_loss,
    )
    start_epoch = to_restore["epoch"]

    start_time = time.time()
    print("Starting DINO training !")
    for epoch in range(start_epoch, args.epochs):
        data_loader.sampler.set_epoch(epoch)

        # ============ training one epoch of DINO ... ============
        train_stats = train_one_epoch(student, teacher, teacher_without_ddp, dino_loss,
            data_loader, optimizer, lr_schedule, wd_schedule, momentum_schedule,
            epoch, fp16_scaler, args)

        # ============ writing logs ... ============
        save_dict = {
            'student': student.state_dict(),
            'teacher': teacher.state_dict(),
            'optimizer': optimizer.state_dict(),
            'epoch': epoch + 1,
            'args': args,
            'dino_loss': dino_loss.state_dict(),
        }
        if fp16_scaler is not None:
            save_dict['fp16_scaler'] = fp16_scaler.state_dict()
        utils.save_on_master(save_dict, os.path.join(args.output_dir, 'checkpoint.pth'))
        #  if args.saveckp_freq and epoch % args.saveckp_freq == 0:
        if epoch >= 85 and args.saveckp_freq and epoch % args.saveckp_freq == 0:
            utils.save_on_master(save_dict, os.path.join(args.output_dir, f'checkpoint{epoch:04}.pth'))
        log_stats = {**{f'train_{k}': v for k, v in train_stats.items()},
                     'epoch': epoch}
        if utils.is_main_process():
            with (Path(args.output_dir) / "log.txt").open("a") as f:
                f.write(json.dumps(log_stats) + "\n")
    total_time = time.time() - start_time
    total_time_str = str(datetime.timedelta(seconds=int(total_time)))
    print('Training time {}'.format(total_time_str))


def train_one_epoch(student, teacher, teacher_without_ddp, dino_loss, data_loader,
                    optimizer, lr_schedule, wd_schedule, momentum_schedule,epoch,
                    fp16_scaler, args):
    metric_logger = utils.MetricLogger(delimiter="  ")
    header = 'Epoch: [{}/{}]'.format(epoch, args.epochs)
    for it, (images, _) in enumerate(metric_logger.log_every(data_loader, 200, header)):
        # update weight decay and learning rate according to their schedule
        it = len(data_loader) * epoch + it  # global training iteration
        for i, param_group in enumerate(optimizer.param_groups):
            param_group["lr"] = lr_schedule[it]
            if i == 0:  # only the first group is regularized
                param_group["weight_decay"] = wd_schedule[it]

        # move images to gpu
        images = [im.cuda(non_blocking=True) for im in images]
        # teacher and student forward passes + compute dino loss
        with torch.cuda.amp.autocast(fp16_scaler is not None):
            teacher_output_g = teacher(images[:2])  # only the 2 global views pass through the teacher
            student_output_g, student_output_pt1, student_output_pt2, student_output_pt3  = student(images)
            loss = dino_loss(teacher_output_g, student_output_g, student_output_pt1, student_output_pt2, student_output_pt3, epoch)

        if not math.isfinite(loss.item()):
            print("Loss is {}, stopping training".format(loss.item()), force=True)
            sys.exit(1)

        # student update
        optimizer.zero_grad()
        param_norms = None
        if fp16_scaler is None:
            loss.backward()
            if args.clip_grad:
                param_norms = utils.clip_gradients(student, args.clip_grad)
            utils.cancel_gradients_last_layer(epoch, student,
                                              args.freeze_last_layer)
            optimizer.step()
        else:
            fp16_scaler.scale(loss).backward()
            if args.clip_grad:
                fp16_scaler.unscale_(optimizer)  # unscale the gradients of optimizer's assigned params in-place
                param_norms = utils.clip_gradients(student, args.clip_grad)
            utils.cancel_gradients_last_layer(epoch, student,
                                              args.freeze_last_layer)
            fp16_scaler.step(optimizer)
            fp16_scaler.update()

        # EMA update for the teacher
        with torch.no_grad():
            m = momentum_schedule[it]  # momentum parameter
            for param_q, param_k in zip(student.module.parameters(), teacher_without_ddp.parameters()):
                param_k.data.mul_(m).add_((1 - m) * param_q.detach().data)

        # logging
        torch.cuda.synchronize()
        metric_logger.update(loss=loss.item())
        metric_logger.update(lr=optimizer.param_groups[0]["lr"])
        metric_logger.update(wd=optimizer.param_groups[0]["weight_decay"])
    # gather the stats from all processes
    metric_logger.synchronize_between_processes()
    print("Averaged stats:", metric_logger)
    return {k: meter.global_avg for k, meter in metric_logger.meters.items()}


class DINOLoss(nn.Module):
    def __init__(self, out_dim, ncrops, warmup_teacher_temp, teacher_temp,
                 warmup_teacher_temp_epochs, nepochs, student_temp=0.1,
                 center_momentum=0.9):
        super().__init__()
        self.student_temp = student_temp
        self.center_momentum = center_momentum
        self.ncrops = ncrops
        self.register_buffer("center_cls", torch.zeros(1, out_dim))
        self.register_buffer("center_pt1", torch.zeros(1, out_dim))
        self.register_buffer("center_pt2", torch.zeros(1, out_dim))
        self.register_buffer("center_pt3", torch.zeros(1, out_dim))
        # we apply a warm up for the teacher temperature because
        # a too high temperature makes the training instable at the beginning
        self.teacher_temp_schedule = np.concatenate((
            np.linspace(warmup_teacher_temp,
                        teacher_temp, warmup_teacher_temp_epochs),
            np.ones(nepochs - warmup_teacher_temp_epochs) * teacher_temp
        ))

    def forward(self, teacher_output_g, student_output_g, student_output_pt1, student_output_pt2, student_output_pt3, epoch):
        """
        Cross-entropy between softmax outputs of the teacher and student networks.
        """
        
        teacher_output_g_cls, teacher_output_g_pt1, teacher_output_g_pt2, teacher_output_g_pt3 = teacher_output_g
        student_output_g_cls, student_output_g_pt1, student_output_g_pt2, student_output_g_pt3 = student_output_g
        student_output_p1_cls, student_output_p1_pt = student_output_pt1
        student_output_p2_cls, student_output_p2_pt = student_output_pt2
        student_output_p3_cls, student_output_p3_pt = student_output_pt3
        
        student_output_g_cls = student_output_g_cls / self.student_temp
        student_output_g_pt1 = student_output_g_pt1 / self.student_temp
        student_output_g_pt2 = student_output_g_pt2 / self.student_temp
        student_output_g_pt3 = student_output_g_pt3 / self.student_temp
        student_output_p1_cls = student_output_p1_cls / self.student_temp
        student_output_p1_pt = student_output_p1_pt / self.student_temp
        student_output_p2_cls = student_output_p2_cls / self.student_temp
        student_output_p2_pt = student_output_p2_pt / self.student_temp
        student_output_p3_cls = student_output_p3_cls / self.student_temp
        student_output_p3_pt = student_output_p3_pt / self.student_temp
        
        
        student_output_g_cls = student_output_g_cls.chunk(2)
        student_output_g_pt1 = student_output_g_pt1.chunk(2)
        student_output_g_pt2 = student_output_g_pt2.chunk(2)
        student_output_g_pt3 = student_output_g_pt3.chunk(2)
        student_output_p1_cls = student_output_p1_cls.chunk(3)
        student_output_p1_pt = student_output_p1_pt.chunk(3)
        student_output_p2_cls = student_output_p2_cls.chunk(3)
        student_output_p2_pt = student_output_p2_pt.chunk(3)
        student_output_p3_cls = student_output_p3_cls.chunk(3)
        student_output_p3_pt = student_output_p3_pt.chunk(3)
        
        student_output_cls_list= student_output_g_cls + student_output_p1_cls + student_output_p2_cls + student_output_p3_cls
        student_output_pt1_list= student_output_g_pt1 + student_output_p1_pt
        student_output_pt2_list= student_output_g_pt2 + student_output_p2_pt
        student_output_pt3_list= student_output_g_pt3 + student_output_p3_pt

        # teacher centering and sharpening
        temp = self.teacher_temp_schedule[epoch]
        teacher_output_g_cls = F.softmax((teacher_output_g_cls - self.center_cls) / temp, dim=-1)
        teacher_output_g_pt1 = F.softmax((teacher_output_g_pt1 - self.center_pt1) / temp, dim=-1)
        teacher_output_g_pt2 = F.softmax((teacher_output_g_pt2 - self.center_pt2) / temp, dim=-1)
        teacher_output_g_pt3 = F.softmax((teacher_output_g_pt3 - self.center_pt3) / temp, dim=-1)
        
        teacher_output_g_cls = teacher_output_g_cls.detach().chunk(2)
        teacher_output_g_pt1 = teacher_output_g_pt1.detach().chunk(2)
        teacher_output_g_pt2 = teacher_output_g_pt2.detach().chunk(2)
        teacher_output_g_pt3 = teacher_output_g_pt3.detach().chunk(2)

        total_loss = 0
        n_loss_terms = 0
        for iq, q in enumerate(teacher_output_g_cls):
            for v in range(len(student_output_cls_list)):
                if v == iq:
                    # we skip cases where student and teacher operate on the same view
                    continue
                loss = torch.sum(-q * F.log_softmax(student_output_cls_list[v], dim=-1), dim=-1)
                total_loss += loss.mean()
                n_loss_terms += 1
        for iq, q in enumerate(teacher_output_g_pt1):
            for v in range(len(student_output_pt1_list)):
                if v == iq:
                    # we skip cases where student and teacher operate on the same view
                    continue
                loss = torch.sum(-q * F.log_softmax(student_output_pt1_list[v], dim=-1), dim=-1)
                total_loss += loss.mean()
                n_loss_terms += 1
        for iq, q in enumerate(teacher_output_g_pt2):
            for v in range(len(student_output_pt2_list)):
                if v == iq:
                    # we skip cases where student and teacher operate on the same view
                    continue
                loss = torch.sum(-q * F.log_softmax(student_output_pt2_list[v], dim=-1), dim=-1)
                total_loss += loss.mean()
                n_loss_terms += 1
        for iq, q in enumerate(teacher_output_g_pt3):
            for v in range(len(student_output_pt3_list)):
                if v == iq:
                    # we skip cases where student and teacher operate on the same view
                    continue
                loss = torch.sum(-q * F.log_softmax(student_output_pt3_list[v], dim=-1), dim=-1)
                total_loss += loss.mean()
                n_loss_terms += 1
        total_loss /= n_loss_terms
        self.update_center(teacher_output_g)
        return total_loss

    @torch.no_grad()
    def update_center(self, teacher_output_g):
        """
        Update center used for teacher output.
        """
        teacher_output_g_cls, teacher_output_g_pt1, teacher_output_g_pt2, teacher_output_g_pt3 = teacher_output_g
        
        batch_center_cls = torch.sum(teacher_output_g_cls, dim=0, keepdim=True)
        dist.all_reduce(batch_center_cls)
        batch_center_cls = batch_center_cls / (len(teacher_output_g_cls) * dist.get_world_size())

        # ema update
        self.center_cls = self.center_cls * self.center_momentum + batch_center_cls * (1 - self.center_momentum)
        
        #part 1
        batch_center_pt1 = torch.sum(teacher_output_g_pt1, dim=0, keepdim=True)
        dist.all_reduce(batch_center_pt1)
        batch_center_pt1 = batch_center_pt1 / (len(teacher_output_g_pt1) * dist.get_world_size())

        # ema update
        self.center_pt1 = self.center_pt1 * self.center_momentum + batch_center_pt1 * (1 - self.center_momentum)
        
        
        #part 2
        batch_center_pt2 = torch.sum(teacher_output_g_pt2, dim=0, keepdim=True)
        dist.all_reduce(batch_center_pt2)
        batch_center_pt2 = batch_center_pt2 / (len(teacher_output_g_pt2) * dist.get_world_size())

        # ema update
        self.center_pt2 = self.center_pt2 * self.center_momentum + batch_center_pt2 * (1 - self.center_momentum)
        
        
        #part 3
        batch_center_pt3 = torch.sum(teacher_output_g_pt3, dim=0, keepdim=True)
        dist.all_reduce(batch_center_pt3)
        batch_center_pt3 = batch_center_pt3 / (len(teacher_output_g_pt3) * dist.get_world_size())

        # ema update
        self.center_pt3 = self.center_pt3 * self.center_momentum + batch_center_pt3 * (1 - self.center_momentum)


class DataAugmentationDINO(object):
    def __init__(self, size, crop_size, global_crops_scale, local_crops_scale, local_crops_number):
        flip_and_color_jitter = transforms.Compose([
            transforms.RandomHorizontalFlip(p=0.5),
            transforms.RandomApply(
                [transforms.ColorJitter(brightness=0.4, contrast=0.4, saturation=0.2, hue=0.1)],
                p=0.8
            ),
            transforms.RandomGrayscale(p=0.2),
        ])
        normalize = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225)),
        ])

        # first global crop
        self.global_transfo1 = transforms.Compose([
            transforms.RandomResizedCrop(size=size, scale=global_crops_scale, interpolation=Image.BICUBIC),
            flip_and_color_jitter,
            utils.GaussianBlur(1.0),
            normalize,
        ])
        # second global crop
        self.global_transfo2 = transforms.Compose([
            transforms.RandomResizedCrop(size=size, scale=global_crops_scale, interpolation=Image.BICUBIC),
            flip_and_color_jitter,
            utils.GaussianBlur(0.1),
            utils.Solarization(0.2),
            normalize,
        ])
        # transformation for the local small crops
        #print(local_crops_scale)
        self.local_crops_number = local_crops_number
        self.local_transfo = transforms.Compose([
            transforms.RandomResizedCrop(size=crop_size, scale=local_crops_scale, interpolation=Image.BICUBIC),
            flip_and_color_jitter,
            utils.GaussianBlur(p=0.5),
            normalize,
        ])

    def __call__(self, image):
        crops = []
        #print('original img', image.size)
        crops.append(self.global_transfo1(image))
        crops.append(self.global_transfo2(image))
        width, height = image.size
        image_test = transforms.functional.crop(image, 0, 0, int(0.5*height), width)
        #print('crop img', image_test.size)
        for _ in range(self.local_crops_number//3):
            crops.append(self.local_transfo(transforms.functional.crop(image, 0, 0, int(0.5*height), width)))
        for _ in range(self.local_crops_number//3):
            crops.append(self.local_transfo(transforms.functional.crop(image, int(0.25*height), 0, int(0.5*height), width)))
        for _ in range(self.local_crops_number//3):
            crops.append(self.local_transfo(transforms.functional.crop(image, int(0.5*height), 0, int(0.5*height), width)))
        return crops


if __name__ == '__main__':
    parser = argparse.ArgumentParser('DINO', parents=[get_args_parser()])
    args = parser.parse_args()
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    train_dino(args)
