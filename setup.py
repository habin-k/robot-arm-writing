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
            # 단독 실행형 로봇 직접 제어 노드 (현재 server/pub_sub 파이프라인에선 미사용)
            'writing_node = cobot_writing.writing_node:main',
        ],
    },
)
