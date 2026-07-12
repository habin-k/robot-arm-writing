from glob import glob

from setuptools import setup

package_name = 'cobot_writing'
font_files = [
    'cobot_writing/fonts/Brother Signature.otf',
    'cobot_writing/fonts/GmarketSansBold.otf',
    'cobot_writing/fonts/GmarketSansLight.otf',
    'cobot_writing/fonts/GmarketSansMedium.otf',
    'cobot_writing/fonts/Griun_Cherry1Spoon-Rg.ttf',
    'cobot_writing/fonts/Helvetica Bold.ttf',
    'cobot_writing/fonts/Helvetica Condensed.ttf',
    'cobot_writing/fonts/Helvetica Extended Medium.ttf',
    'cobot_writing/fonts/Helvetica Extended.ttf',
    'cobot_writing/fonts/Helvetica Light.ttf',
]

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
        ('lib/python3.10/site-packages/' + package_name + '/fonts', font_files),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='TODO',
    maintainer_email='todo@todo.todo',
    description='Cobot writing package for Doosan M0609',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'paper_sensor_publisher = cobot_writing.paper_sensor_publisher:main',
            'task_manager = cobot_writing.task_manager_node:main',
            'writer = cobot_writing.writer:main',
        ],
    },
)
