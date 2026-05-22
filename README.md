# RealSense L515 — Mapeamento 3D em Tempo Real no Jetson AGX Orin

Pipeline completo em dois passos:

1. **Step 1** — Container Docker com librealsense + CUDA: valida a câmera, exibe streams e nuvem de pontos  
2. **Step 2** — Container Docker com ROS 2 Humble + RTAB-Map: mapeamento 3D em tempo real com RViz2

---

## Hardware e Software Necessários

| Item | Requisito |
|------|-----------|
| Hardware | NVIDIA Jetson AGX Orin |
| JetPack | 6.1 (L4T R36.4.x) |
| CUDA | 12.6 · SM 8.7 (Ampere) |
| Câmera | Intel RealSense L515 (LiDAR) |
| Porta USB | USB 3.0 SuperSpeed (obrigatório — USB 2.0 causa falha) |
| Memória RAM | ≥ 16 GB recomendado para o build |
| Espaço em disco | ≥ 20 GB livres (builder ~8 GB + runtime ~2.5 GB + mapping ~5 GB) |

---

## Pré-requisitos no Host

### 1. Docker com NVIDIA runtime

```bash
# Verificar se o Docker está instalado
docker --version

# Instalar nvidia-container-toolkit (se não tiver)
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list \
    | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit

# Configurar o runtime padrão (editar /etc/docker/daemon.json)
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Verificar
docker info | grep -i runtime
```

O arquivo `/etc/docker/daemon.json` deve conter:
```json
{
    "runtimes": {
        "nvidia": {
            "path": "nvidia-container-runtime",
            "runtimeArgs": []
        }
    },
    "default-runtime": "nvidia"
}
```

### 2. BuildKit habilitado

```bash
# Verificar (deve retornar a versão)
docker buildx version

# Se não estiver disponível:
export DOCKER_BUILDKIT=1
# Para persistir, adicione ao ~/.bashrc:
echo 'export DOCKER_BUILDKIT=1' >> ~/.bashrc
```

### 3. Permissões de grupo

```bash
sudo usermod -aG docker,video,plugdev $USER
# Fazer logout e login novamente para aplicar
```

---

## Estrutura do Projeto

```
Realsense/
├── Dockerfile              # Step 1: librealsense 2.53.1 + CUDA 12.6
├── Dockerfile.mapping      # Step 2: ROS 2 Humble + RTAB-Map (herda do Step 1)
├── docker-compose.yml      # Alternativa ao run.sh para o Step 1
├── .dockerignore
├── scripts/
│   ├── build.sh            # Build da imagem Step 1 (realsense-l515:latest)
│   ├── run.sh              # Inicia container Step 1 com X11, CUDA e USB
│   ├── validate.sh         # Verifica pré-requisitos no host
│   ├── validate_realsense.py   # Validação da câmera dentro do container
│   ├── view_streams.py     # Visualizador depth + color em tempo real (OpenCV)
│   ├── view_pointcloud.py  # Visualizador de nuvem de pontos 3D (Open3D)
│   ├── build_mapping.sh    # Build da imagem Step 2 (realsense-mapping:latest)
│   ├── run_mapping.sh      # Inicia mapeamento 3D (RTAB-Map + RViz2)
│   ├── camera_live.py      # Visualizador simples (câmera ao vivo)
│   └── ver_camera.sh       # Diagnóstico rápido da câmera
├── mapping/
│   ├── l515_rtabmap.launch.py  # Launch ROS 2: câmera + IMU + RTAB-Map + RViz2
│   ├── l515_mapping.rviz       # Configuração do RViz2 para mapeamento
│   └── entrypoint.sh           # Sourcing dos ambientes ROS no container
├── udev/
│   └── setup_udev.sh       # Instala regras udev no host (sudo, uma vez)
└── workspace/              # Pasta montada em /workspace dentro do container
```

---

## Passo a Passo — Do Zero ao Mapeamento 3D

### Etapa 0 — Verificar pré-requisitos

```bash
# Clone o repositório
git clone https://github.com/henrick-souza/Realsense.git
cd Realsense

# Executar verificação completa do host
./scripts/validate.sh
```

O script verifica Docker, NVIDIA runtime, CUDA, udev rules, câmera e permissões.  
Corrija todos os itens `[FAIL]` antes de continuar.

---

### Etapa 1 — Câmera + CUDA (Step 1)

#### 1.1 Build da imagem

```bash
./scripts/build.sh
```

> **Tempo estimado:** 35–50 min na primeira vez. Nas seguintes, ~5 min (ccache aquecido).  
> **Tamanho final:** ~2.5 GB (runtime) + ~8 GB temporários no builder.

Flags opcionais:
```bash
./scripts/build.sh --no-cache                    # rebuild completo
./scripts/build.sh --librealsense 2.54.1         # versão diferente
./scripts/build.sh --tag realsense-l515:v2       # tag customizada
```

#### 1.2 Instalar regras udev (apenas uma vez)

```bash
sudo ./udev/setup_udev.sh
# Após o script: desconecte e reconecte a câmera L515
```

#### 1.3 Verificar câmera no host

```bash
lsusb | grep 8086   # deve mostrar a câmera Intel
```

#### 1.4 Iniciar o container

```bash
./scripts/run.sh
```

O script configura automaticamente X11, xauth, coleta dispositivos hidraw (IMU) e inicia o container.

#### 1.5 Validar câmera dentro do container

```bash
# Teste básico (import + detecção do dispositivo)
python3 /opt/validate_realsense.py

# Teste com captura de 30 frames
python3 /opt/validate_realsense.py --stream

# Teste com filtro CUDA
python3 /opt/validate_realsense.py --cuda
```

#### 1.6 Visualizar streams

```bash
# Depth + color lado a lado (OpenCV)
python3 /opt/view_streams.py

# Nuvem de pontos 3D (Open3D)
python3 /opt/view_pointcloud.py

# Salvar a nuvem de pontos ao sair
python3 /opt/view_pointcloud.py --save
```

**Controles do view_streams.py:**

| Tecla | Ação |
|-------|------|
| `Q` / `Esc` | Sair |
| `S` | Salvar frame em `/workspace/` |
| `Space` | Pausar / retomar |
| `C` | Trocar colormap de profundidade |
| `F` | Ativar/desativar filtro temporal |

**Controles do view_pointcloud.py:** arraste para rotacionar, scroll para zoom, `R` para resetar câmera.

---

### Etapa 2 — Mapeamento 3D em Tempo Real (Step 2)

> **Pré-requisito:** a imagem `realsense-l515:latest` do Step 1 deve existir.

#### 2.1 Build da imagem de mapeamento

```bash
./scripts/build_mapping.sh
```

> **Tempo estimado:** 10–20 min. Instala ROS 2 Humble + RTAB-Map + realsense-ros compilado do source.  
> **Tamanho final:** ~5 GB.

#### 2.2 Iniciar o mapeamento

```bash
./scripts/run_mapping.sh
```

O script inicia automaticamente:
- Driver da câmera L515 (realsense2_camera)
- Filtro IMU Madgwick (gyro + accel → quaternion)
- Odometria visual RGB-D (RTAB-Map)
- SLAM + construção do mapa 3D (RTAB-Map)
- RViz2 com visualização do mapa em tempo real

**Dica de uso:** mova a câmera devagar e de forma suave. Movimentos bruscos causam falha na odometria. O mapa 3D aparece no RViz2 conforme o ambiente é explorado.

#### 2.3 Salvar o mapa

O mapa é salvo automaticamente em `/root/.ros/rtabmap.db` dentro do container. Para exportar:

```bash
# Dentro do container (em outro terminal)
docker exec -it realsense-mapping bash
ros2 run rtabmap_ros rtabmap_export --ros-args \
    -p "database_path:=/root/.ros/rtabmap.db" \
    -p "output_path:=/workspace/mapa_final.ply"
```

O arquivo `.ply` ficará disponível na pasta `workspace/` do host.

---

## Alternativa: Docker Compose (Step 1 apenas)

```bash
export DISPLAY=:0
xhost +local:docker
docker compose up -d
docker compose exec realsense bash
docker compose down
```

---

## Perfis de Stream da L515

| Stream | Resolução | Formato | FPS |
|--------|-----------|---------|-----|
| Depth  | 1024×768  | Z16     | 30  |
| Depth  | 640×480   | Z16     | 30  |
| Color  | 1920×1080 | BGR8    | 30  |
| Color  | 1280×720  | BGR8    | 30  |
| Gyro   | —         | —       | 400 Hz |
| Accel  | —         | —       | 100 Hz |

Unidade de profundidade: 0.25 mm (valor × 0.00025 = metros). Alcance: 0.25 m a 9 m.

---

## Troubleshooting

### Câmera não encontrada dentro do container

```bash
# Verificar se a câmera está visível no host
lsusb | grep 8086

# Verificar se as regras udev foram instaladas
ls /etc/udev/rules.d/99-realsense-libusb.rules

# Diagnóstico rápido com acesso total
docker run --rm --privileged --runtime nvidia realsense-l515:latest \
    python3 /opt/validate_realsense.py
```

### Erro de import do pyrealsense2

```bash
find /usr/local/lib -name "pyrealsense2*.so"
python3 -c "import sys; print('\n'.join(sys.path))"
```

### RViz2 ou realsense-viewer com tela em branco

```bash
# No host:
xhost +local:docker

# Dentro do container:
glxgears   # testa OpenGL/X11 — deve mostrar engrenagens girando
```

### DISPLAY não definido

```bash
# No host, antes de rodar o container:
export DISPLAY=:0    # ou :1, dependendo do display ativo
echo $DISPLAY
```

### L515 com USB 2.0 (frames dropados)

A L515 exige USB 3.0 SuperSpeed. Verificar dentro do container:

```python
import pyrealsense2 as rs
for dev in rs.context().query_devices():
    print(dev.get_info(rs.camera_info.usb_type_descriptor))  # espera 3.1 ou 3.2
```

### IMU da L515 não funciona (hid_sensor_hub)

```bash
# Carregar módulo (temporário)
sudo modprobe hid-sensor-hub

# Persistir entre reboots
echo 'hid-sensor-hub' | sudo tee /etc/modules-load.d/realsense-imu.conf
```

### RTAB-Map perdendo odometria

Sintomas: mapa vai em direção errada ou loop closure falha.

- Reduza a velocidade de movimento da câmera
- Garanta iluminação adequada (a L515 é LiDAR mas o RTAB-Map usa features visuais)
- Aumente `Vis/MinInliers` para `8` ou `10` em `mapping/l515_rtabmap.launch.py` para exigir mais correspondências

---

## Decisões de Design

**librealsense 2.53.1** — Intel anunciou End-of-Life da L515 na versão 2.54.1. Esta é a última versão com suporte ativo e testes específicos para a L515. Para usar versão mais nova: `./scripts/build.sh --librealsense 2.54.1`

**Backend RSUSB** — O backend V4L2 exige o módulo de kernel `uvcvideo` e acesso a `/dev/video*` dentro do container. O RSUSB usa libusb diretamente — só precisa de `/dev/bus/usb` e das regras udev, sem modificações no kernel do host.

**nvidia/cuda:12.6.0-devel como builder** — `docker build` não usa o NVIDIA runtime, então os headers CUDA e o `nvcc` precisam estar embutidos na imagem durante o build. O estágio runtime usa a variante menor `cuda:runtime`; em execução, `--runtime=nvidia` sobrepõe as bibliotecas GPU do host Jetson.

**ccache + ninja** — O primeiro build popula o ccache (~5 GB). Builds subsequentes recompilam apenas o que mudou (~5 min em vez de ~50 min).

**RTAB-Map via apt (sub-pacotes)** — O meta-pacote `ros-humble-rtabmap-ros` puxa `librealsense2 2.57.7` via apt, quebrando o driver compilado no Step 1. Por isso, os sub-pacotes do RTAB-Map são instalados individualmente (`rtabmap-slam`, `rtabmap-odom`, etc.) e o `realsense-ros` é compilado do source.

---

## Próximo Passo: Nvblox + Isaac ROS

Step 3 poderá herdar diretamente da imagem de mapeamento:

```dockerfile
FROM realsense-mapping:latest
# + Isaac ROS Nvblox
```

Os frames depth + color alinhados da L515 já estão no formato correto para o Nvblox.  
**Atenção:** o Nvblox foi otimizado para câmeras stereo (D435/D455). Com a L515 LiDAR, ajuste `voxel_size` e `truncation_distance` para o perfil de ruído da L515.
