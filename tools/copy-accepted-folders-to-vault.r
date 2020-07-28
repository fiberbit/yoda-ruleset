#!/usr/bin/irule -F

copyToVault {
        writeLine("stdout", "test");
	# Copy research folder to vault.
	# This script is kept as dumb as possible.
	# All processing and error handling is done by iiFolderSecure
	*ContInxOld = 1;
	msiAddSelectFieldToGenQuery("COLL_NAME", "", *GenQInp);
	msiAddConditionToGenQuery("META_COLL_ATTR_NAME", "=", UUORGMETADATAPREFIX ++ "cronjob_copy_to_vault", *GenQInp);
	msiAddConditionToGenQuery("META_COLL_ATTR_VALUE", "=", CRONJOB_PENDING, *GenQInp);

        writeLine("stdout", "test2");

	msiExecGenQuery(*GenQInp, *GenQOut);
	msiGetContInxFromGenQueryOut(*GenQOut, *ContInxNew);

	while(*ContInxOld > 0) {
                writeLine("stdout", "test3");
		foreach(*row in *GenQOut) {
			*folder = *row.COLL_NAME;
                        writeLine("stdout", *folder);
			# When iiFolderSecure fails continue with the other folders.
                        *errorcode = '0';
                        writeLine("stdout", "test5");
                        rule_folder_secure(*folder, *errorcode);
                        writeLine("stdout", "erna");
			if (*errorcode == '0') {
				*cronjobState = UUORGMETADATAPREFIX ++ "cronjob_copy_to_vault=" ++ CRONJOB_OK;
				msiString2KeyValPair(*cronjobState, *cronjobStateKvp);
				*err = errormsg(msiRemoveKeyValuePairsFromObj(*cronjobStateKvp, *folder, "-C"), *msg);
			}
		}

		*ContInxOld = *ContInxNew;
		if(*ContInxOld > 0) {
			msiGetMoreRows(*GenQInp, *GenQOut, *ContInxNew);
		}
	}
	msiCloseGenQuery(*GenQInp, *GenQOut);
}
input null
output ruleExecOut
