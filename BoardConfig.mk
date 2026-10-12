#
# Copyright (C) 2018 The TwrpBuilder Open-Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

LOCAL_PATH := device/coolpad/cp3320a

TARGET_ARCH := arm
TARGET_ARCH_VARIANT := armv7-a-neon
TARGET_CPU_VARIANT := cortex-a7
TARGET_CPU_ABI := armeabi-v7a
TARGET_CPU_ABI2 := armeabi
TARGET_BOARD_PLATFORM := msm8909
TARGET_NO_BOOTLOADER := true
TARGET_NO_RADIOIMAGE := true

TARGET_PREBUILT_KERNEL := $(LOCAL_PATH)/kernel
BOARD_KERNEL_BASE := 0x80000000
BOARD_KERNEL_PAGESIZE := 2048
BOARD_MKBOOTIMG_ARGS := --kernel_offset 0x00008000 --ramdisk_offset 0x01000000 --second_offset 0x00f00000 --tags_offset 0x00000100 --dt $(LOCAL_PATH)/dt.img
BOARD_KERNEL_CMDLINE := console=ttyHSL0,115200,n8 androidboot.console=ttyHSL0 androidboot.hardware=qcom user_debug=31 msm_rtb.filter=0x3F ehci-hcd.park=3 androidboot.bootdevice=7824900.sdhci lpm_levels.sleep_disabled=1 earlyprintk androidboot.selinux=permissive
BOARD_RECOVERYIMAGE_PARTITION_SIZE := 16777216
BOARD_FLASH_BLOCK_SIZE := 131072
TARGET_USERIMAGES_USE_EXT4 := true
TARGET_RECOVERY_FSTAB := $(LOCAL_PATH)/recovery.fstab

TW_THEME := portrait_mdpi
TW_INPUT_BLACKLIST := "hbtp_vm"
TW_IGNORE_MAJOR_AXIS_0 := true
TW_BRIGHTNESS_PATH := /sys/class/leds/lcd-backlight/brightness
RECOVERY_GRAPHICS_FORCE_USE_LINELENGTH := true
TW_EXCLUDE_MTP := true
TW_EXTRA_LANGUAGES := false
TW_EXCLUDE_TWRPAPP := true
TW_EXCLUDE_SUPERSU := true
TW_NO_EXFAT := true
TW_NO_USB_STORAGE := true

