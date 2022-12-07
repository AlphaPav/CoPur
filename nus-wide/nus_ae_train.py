import argparse
import os
import time
import numpy as np
import copy 
from utils.nus_utils import get_local_outputs,load_data
import tensorflow as tf
from models.AE import AE_NUS as AutoEncoder

def parse_path(args):
    SavedPaths=[]
    # _mode = 'normal'
    # savefolder= '{}_{}i_{}t_try{}'.format(_mode, args.num_img_clients, args.num_text_clients, args.seed)
    for i in range(args.num_img_clients):
        _dir= os.path.join(args.path_predix, 'img_{}_{}'.format(args.img_feature_div[i], args.img_feature_div[i+1]))
        SavedPaths.append(_dir)
    for i in range(args.num_text_clients):
        _dir= os.path.join(args.path_predix, 'text_{}_{}'.format(args.text_feature_div[i], args.text_feature_div[i+1] ))
        SavedPaths.append(_dir)
    
    print(SavedPaths)
    return SavedPaths

def create_models(args):
    from models.LocalModel import VFLPassiveModel

    LocalModels= []
    for i in range(args.num_clients):
        local_model = VFLPassiveModel(emb_dim=args.emb_dim)
        local_model.built = True
        
        local_model.load_weights(os.path.join(args.local_paths[i],'best_checkpoints')) 
        local_model.trainable = False
        LocalModels.append(local_model)

   
    return LocalModels
    
def parse_command():
    parser = argparse.ArgumentParser()

    parser.add_argument('--emb_dim', type=int, default=60)
    parser.add_argument('--batch_size', type=int, default=256) 
    parser.add_argument('--ae_epochs', type=int, default=10)
    parser.add_argument('--ae_lr', type=float, default=0.001)
    parser.add_argument('--num_class', type=int, default=5)
    parser.add_argument('--seed', type=int, default=1)

    parser.add_argument('--num_test_samples', type=int, default=10000)
    parser.add_argument('--num_train_samples', type=int, default=60000)
    
    parser.add_argument('--path_predix', type=str, default='nus_results')
    parser.add_argument('--mode', type=str, default='normal',
                        choices=[
                            'normal',
                        ])
    parser.add_argument('--img_feature_div', nargs='+', type=int, default=[0, 360, 634])
    parser.add_argument('--text_feature_div', nargs='+', type=int, default=[0,500, 1000])
    
    parser.add_argument('--vis',  action='store_true')
    
    
    args = parser.parse_args()
    if args.seed is not None:
        import random
        random.seed(args.seed)
        tf.random.set_seed(args.seed)
    args.num_img_clients= len(args.img_feature_div)-1
    args.num_text_clients= len(args.text_feature_div)-1
    args.num_clients = args.num_img_clients+ args.num_text_clients
  
    args.path_predix_load = args.path_predix
    savefolder= '{}_{}i_{}t_try{}'.format(args.mode, args.num_img_clients, args.num_text_clients, args.seed)
    args.path_predix=os.path.join(args.path_predix, savefolder)
    local_paths =  parse_path(args)
    args.local_paths= local_paths
    print("save to", args.path_predix)
    args.top_k= ['buildings', 'grass', 'animal', 'water', 'person'] 

    return args 



args = parse_command()
if args.vis:
    from tensorboardX import SummaryWriter
    import datetime
    current_time = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    log_dir = os.path.join(args.path_predix,current_time)
    args.train_writer = tf.summary.create_file_writer(log_dir)


x_train, (test_images, test_texts), y_train, y_test = load_data(args)
LocalModels = create_models(args)
autoencoder_model=AutoEncoder(out_dim= args.num_clients * args.emb_dim)
(x_train_images, x_train_texts) = x_train
LocalOutputs= get_local_outputs(args.num_img_clients, x_train_images, args.img_feature_div, 
                    args.num_text_clients, x_train_texts, args.text_feature_div, LocalModels) 
H_input=tf.concat(LocalOutputs,1)
rae_loss_object=tf.keras.losses.MeanSquaredError()
rae_optimizer = tf.keras.optimizers.SGD(learning_rate=args.ae_lr)
rae_train_loss=  tf.keras.metrics.Mean(name='rae_train_loss')

def train_ae(epoch):
    
    train_ds = tf.data.Dataset.from_tensor_slices(
        (H_input)).batch(args.batch_size)
    
    ae_step= len(train_ds) *epoch  
    for h_input  in train_ds:
        ae_step+=1
        with tf.GradientTape() as active_tape:
            rae_output, _ = autoencoder_model(h_input)
            loss= rae_loss_object(rae_output, h_input) 
        
        rae_gradients = active_tape.gradient(loss, autoencoder_model.trainable_variables)
        rae_optimizer.apply_gradients(zip(rae_gradients, autoencoder_model.trainable_variables))

        rae_train_loss(loss)
        if args.vis:
            with args.train_writer.as_default():
                tf.summary.scalar('train_AE_loss', loss, step=ae_step)
    


for epoch in range(args.ae_epochs):
    start= time.time() 
    train_ae(epoch)
    end= time.time()  
    print("AE training epoch: ", epoch, "loss", rae_train_loss.result(), "time: ",time.time()- start)
    rae_train_loss.reset_states()
    autoencoder_model.save_weights(os.path.join(args.path_predix, 'ae_ckpt.tf'))   



