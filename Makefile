# Original minimal libnx build. No ROMFS, embedded banks, icons or game data.
.SUFFIXES:
.DELETE_ON_ERROR:
ifeq ($(strip $(DEVKITPRO)),)
$(error Set DEVKITPRO and use the devkitPro MSYS2 shell)
endif
include $(DEVKITPRO)/libnx/switch_rules

TARGET := vore-nx
APP_TITLE := vore-nx ROM preparation
APP_AUTHOR := vore-nx contributors
APP_VERSION := 0.1.1
BUILD := build
PYTHON ?= python
ARCH := -march=armv8-a+crc+crypto -mtune=cortex-a57 -mtp=soft -fPIE
CXXFLAGS := -g -O2 -Wall -Wextra -Werror -std=c++17 -ffunction-sections -fdata-sections $(ARCH) -fno-rtti -fno-exceptions -ffile-prefix-map=$(TOPDIR)=. $(INCLUDE)
LDFLAGS = -specs=$(DEVKITPRO)/libnx/switch.specs -g $(ARCH) -Wl,-Map,$(TARGET).map
LIBS := -lnx

ifneq ($(BUILD),$(notdir $(CURDIR)))
export OUTPUT := $(CURDIR)/$(TARGET)
export TOPDIR := $(CURDIR)
export VPATH := $(CURDIR)/source
export DEPSDIR := $(CURDIR)/$(BUILD)
export INCLUDE := -I$(CURDIR)/include -isystem $(LIBNX)/include
export LIBPATHS := -L$(LIBNX)/lib
export LD := $(CXX)
export OFILES := switch_main.o cartridge.o sha256.o
export NROFLAGS := --nacp=$(CURDIR)/$(TARGET).nacp

.PHONY: all $(BUILD)
all: $(BUILD)
$(BUILD):
	@mkdir -p $(BUILD)
	@$(MAKE) --no-print-directory -C $(BUILD) -f $(CURDIR)/Makefile
else
.PHONY: all
all: $(OUTPUT).nro
$(OUTPUT).nro: $(OUTPUT).elf $(OUTPUT).nacp $(TOPDIR)/tools/sanitize_sdk_paths.py $(TOPDIR)/Makefile
	@elf2nro $< $@ $(NROFLAGS)
	@$(PYTHON) $(TOPDIR)/tools/sanitize_sdk_paths.py $@
$(OUTPUT).elf: $(OFILES)
-include $(OFILES:.o=.d)
endif
