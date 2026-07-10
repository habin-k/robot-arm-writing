from setuptools import setup

package_name = 'cobot_writing'

setup(
    name=package_name,
    version='0.0.0',
    # HersheyFonts 하위 폴더는 미사용(소스 없음)이라 최상위 패키지만 포함.
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='dongmin',
    maintainer_email='dongmin@todo.todo',
    description='Cobot writing package using Hershey Fonts for Doosan M0609',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            # 아두이노 종이 감지 센서 → 'paper_sensor'(Bool, True=종이 있음) 발행.
            # 서버 ros_node.py 가 구독해 /ws/robot 으로 HMI 에 전달한다.
            'paper_sensor_publisher = cobot_writing.paper_sensor_publisher:main',
            # 작업 매니저: 펜 파지→글쓰기→도장→종이 배출 시퀀스 (writer/paper_ejector 사용).
            #   ros2 run cobot_writing task_manager --ros-args -p check_grip:=false
            'task_manager = cobot_writing.task_manager_node:main',
            # 위 task_manager 에 펜/도장 파지 실패 시 재파지(grip_with_retry) 추가한 테스트본.
            #   ros2 run cobot_writing task_manager_test --ros-args -p check_grip:=false
            'task_manager_test = cobot_writing.task_manager_node_test:main',
            # 아래 둘은 단독 모션 테스트용 (task_manager 가 클래스로도 사용).
            'writer = cobot_writing.writer:main',
            'paper_ejector = cobot_writing.paper_ejector_node:main',
        ],
    },
)
