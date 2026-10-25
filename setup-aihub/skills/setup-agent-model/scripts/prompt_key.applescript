on run argv
    set targetPath to item 1 of argv
    set response to display dialog "AIhub Key will be saved to the confirmed native configuration:" & return & targetPath default answer "" with hidden answer buttons {"Cancel", "Save"} default button "Save" cancel button "Cancel" with title "Setup AIHub"
    return text returned of response
end run
