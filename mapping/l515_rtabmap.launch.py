import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():

    # Parâmetros compartilhados entre odometria e SLAM
    rtabmap_params = {
        'frame_id':                          'camera_link',
        'odom_frame_id':                     'odom',
        'subscribe_depth':                   True,
        'subscribe_odom_info':               True,
        'wait_imu_to_init':                  True,
        'approx_sync':                       True,
        'approx_sync_max_interval':          0.02,
        # L515: range 0.25–9m
        'Grid/RangeMin':                     '0.25',
        'Grid/RangeMax':                     '8.0',
        'Grid/CellSize':                     '0.05',
        'Grid/3D':                           'true',
        # Matching visual (robusto em interiores texturizados)
        'Reg/Strategy':                      '0',
        'Vis/MinInliers':                    '6',
        'Vis/MaxFeatures':                   '1000',
        'Vis/FeatureType':                   '6',
        'OdomF2M/MaxSize':                   '5000',
        'RGBD/LinearUpdate':                 '0.01',
        'RGBD/AngularUpdate':                '0.01',
        # Otimização do grafo
        'RGBD/OptimizeFromGraphEnd':         'false',
        'RGBD/OptimizeMaxError':             '3.0',
        'RGBD/ProximityBySpace':             'true',
        'RGBD/NeighborLinkRefining':         'true',
        # Publicar point cloud global para RViz
        'RTAB-Map/PublishLastSignature':     'true',
    }

    # Tópicos da câmera → entradas do RTAB-Map
    rtabmap_remaps = [
        ('rgb/image',       '/camera/color/image_raw'),
        ('rgb/camera_info', '/camera/color/camera_info'),
        ('depth/image',     '/camera/aligned_depth_to_color/image_raw'),
        ('imu',             '/imu/data'),
    ]

    return LaunchDescription([

        DeclareLaunchArgument('rviz',
            default_value='true',
            description='Abrir RViz2 com visualização do mapa'),

        # ── Nó 0: TF estático — camera_imu_optical_frame alias de camera_gyro_optical_frame
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='camera_imu_tf',
            arguments=['0', '0', '0', '0', '0', '0',
                       'camera_gyro_optical_frame', 'camera_imu_optical_frame'],
        ),

        # ── Nó 1: Driver da câmera L515 ──────────────────────────────────────
        Node(
            package='realsense2_camera',
            executable='realsense2_camera_node',
            name='camera',
            namespace='camera',
            output='screen',
            parameters=[{
                'depth_module.profile':   '640x480x30',
                'rgb_camera.profile':     '640x480x30',
                'align_depth.enable':     True,
                'enable_sync':            True,
                'pointcloud.enable':      False,
                'enable_gyro':            True,
                'enable_accel':           True,
                'unite_imu_method':       2,
                'enable_confidence':      True,
            }],
        ),

        # ── Nó 2: Filtro IMU (gyro+accel → quaternion) ───────────────────────
        Node(
            package='imu_filter_madgwick',
            executable='imu_filter_madgwick_node',
            name='imu_filter',
            output='screen',
            parameters=[{
                'use_mag':     False,
                'world_frame': 'enu',
                'publish_tf':  False,
                'gain':        0.01,
            }],
            remappings=[
                ('imu/data_raw', '/camera/imu'),
                ('imu/data',     '/imu/data'),
            ],
        ),

        # ── Nó 3: Odometria visual RGB-D ─────────────────────────────────────
        Node(
            package='rtabmap_odom',
            executable='rgbd_odometry',
            name='rtabmap_odometry',
            output='screen',
            parameters=[rtabmap_params],
            remappings=rtabmap_remaps,
        ),

        # ── Nó 4: SLAM + construção do mapa 3D ───────────────────────────────
        Node(
            package='rtabmap_slam',
            executable='rtabmap',
            name='rtabmap',
            output='screen',
            parameters=[rtabmap_params],
            remappings=rtabmap_remaps,
            arguments=['--delete_db_on_start'],
        ),

        # ── Nó 5: RViz2 ──────────────────────────────────────────────────────
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            condition=IfCondition(LaunchConfiguration('rviz')),
            arguments=['-d', '/opt/mapping/l515_mapping.rviz'],
            output='screen',
        ),
    ])
