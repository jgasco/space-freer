import json, photos
from os.path import join
from datetime import datetime, timedelta
from io import BytesIO
from smb.SMBConnection import SMBConnection
from objc_util import ObjCInstance

class SmbServer(object):
    def __init__(self, name: str, ipAddress: str, shareName: str,
    destImagePath: str, destVideoPath: str, username: str, password: str) -> None:
        self.name = name
        self.ipAddress = ipAddress
        self.shareName = shareName
        self.destImagePath = destImagePath
        self.destVideoPath = destVideoPath
        self.username = username
        self.password = password

class TimePeriod(object):
    units = ("days", "weeks", "years")
    def __init__(self, value: int, units: str) -> None:
        self.value = value
        if units in TimePeriod.units:
            self.units = units
        else:
            raise ValueError(f"units argument must be one of the following: {TimePeriod.units}")
        self.timedelta = self._get_timedelta()

    def _get_timedelta(self) -> timedelta:
        if self.units == TimePeriod.units[0]:
            td = timedelta(days=self.value)
        elif self.units == TimePeriod.units[1]:
            td = timedelta(weeks=self.value)
        else:
            number_of_weeks = self.value * 52
            td = timedelta(weeks=number_of_weeks)
        return td

class SpaceFreer(object):
    def __init__(self, smbServer: "dict[str, any]", localDeleteTimePeriod: "dict[str, any]") -> None:
        self.smbServer = SmbServer(**smbServer)
        self.localDeleteTimePeriod = TimePeriod(**localDeleteTimePeriod)
        self.localDeleteDateTime = datetime.now() - self.localDeleteTimePeriod.timedelta
        self.smbCnxn = SMBConnection(self.smbServer.username, self.smbServer.password, "iPhone", self.smbServer.name)
        self.smbCnxn.connect(self.smbServer.ipAddress)
        self.assetsToBeDeleted = []

    def _move_files_to_smb_server(self, media_type: str, timeout_per_file: int) -> int:
        dest_path = self.smbServer.destImagePath if media_type == "image" else self.smbServer.destVideoPath
        remote_file_names: "set[str]" = {sf.filename for sf in self.smbCnxn.listPath(self.smbServer.shareName, dest_path) if sf.isNormal}
        remote_copy_count = 0
        assets = photos.get_assets(media_type)
        for asset in assets:
            asset_file_name = str(ObjCInstance(asset).filename())
            if asset_file_name not in remote_file_names:
                dest_file_path = join(dest_path, asset_file_name)
                #asset.get_image_data() does not get all the bytes from video files for some reason
                self.smbCnxn.storeFile(self.smbServer.shareName, dest_file_path, asset.get_image_data(), timeout_per_file)
                remote_copy_count += 1
            if asset.can_delete and asset.creation_date < self.localDeleteDateTime:
                self.assetsToBeDeleted.append(asset)
        return remote_copy_count       

    def run(self):
        dt_start = datetime.now()
        try:
            print("moving image files to SMB server...\n")
            remote_copy_count = self._move_files_to_smb_server("image", 30)
            print(remote_copy_count, "image(s) were copied to the SMB server\n")
            # print("moving video files to SMB server...\n")
            # self._move_files_to_smb_server("video", 2048)
        finally:
            self.smbCnxn.close()
            if self.assetsToBeDeleted:
                print(f"{len(self.assetsToBeDeleted)} items from the photos library are older than {self.localDeleteTimePeriod.value} {self.localDeleteTimePeriod.units} and are now being deleted...\n")
                photos.batch_delete(self.assetsToBeDeleted)
        print(f"Done (elapsed time: {datetime.now() - dt_start})")

if __name__ == "__main__":
    with open("config.json", "r") as f:
        space_freer = SpaceFreer(**json.load(f))
    space_freer.run()