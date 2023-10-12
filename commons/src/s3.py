from os import listdir, makedirs
from os.path import join as path_join
from os.path import sep as os_sep

import boto3


class S3Interface:
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#s3
    def __init__(self, bucket_name: str, aws_id: str, aws_key: str):
        self.bucket_name = bucket_name
        self.client = boto3.client(
            "s3",
            aws_access_key_id=aws_id,
            aws_secret_access_key=aws_key,
        )
        self.tmp_root = "/data"

    def build_local_dir(
        self,
        prefix_enviroment: str,
        prefix_subdir: str,
        package_name: str,
        separator: str = "/",
    ):
        local_dir: str = os_sep.join(
            [
                self.tmp_root,
                prefix_enviroment,
                *[a for a in prefix_subdir.split(separator) if len(a) > 0],
                package_name,
            ]
        )

        # TODO validar que tmp_root exista y que sea abs

        makedirs(local_dir, mode=777, exist_ok=True)

        return local_dir

    def download_package(
        self,
        prefix_enviroment: str,
        prefix_subdir: str,
        package_name: str,
        separator: str = "/",
    ):
        local_dir: str = self.build_local_dir(
            prefix_enviroment,
            prefix_subdir,
            package_name,
            separator,
        )

        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/list_objects_v2.html
        response = self.client.list_objects_v2(
            Bucket=self.bucket_name,
            Delimiter=separator,
            Prefix=f"{prefix_enviroment}{separator}{prefix_subdir}{separator}{package_name}{separator}",
        )

        print(response)

        for s3_object in response["Contents"]:
            s3_key: str = s3_object["Key"]

            if s3_key.endswith(separator):
                continue
            # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/download_file.html
            self.client.download_file(self.bucket_name, s3_key, f"{self.tmp_root}{os_sep}{s3_key}")

        return local_dir

    def upload_package(
        self,
        prefix_enviroment: str,
        prefix_subdir: str,
        package_name: str,
        separator: str = "/",
    ):
        local_dir: str = self.build_local_dir(
            prefix_enviroment,
            prefix_subdir,
            package_name,
            separator,
        )

        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/upload_file.html
        for file_name in listdir(local_dir):
            file_path = path_join(local_dir, file_name)
            self.client.upload_file(
                file_path,
                self.bucket_name,
                file_path.replace(self.tmp_root+os_sep, "").replace(os_sep, separator),
            )
