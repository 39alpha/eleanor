module eq36_data1

    implicit none

    public :: openin
    public :: closein
    public :: indath
    public :: indata

contains

    subroutine openin(filename, logical_unit, errno)
        character(*), intent(in) :: filename
        integer, intent(out) :: logical_unit, errno

        logical exists
        character*8 uformo

        inquire(file=filename, exist=exists, formatted=uformo)
        if (.not. exists) then
            errno = 404
            go to 999
        end if

        open(file=filename, form='unformatted', newunit=logical_unit, err=10)
        go to 999

        10 errno = 403

        999 continue
    end

    subroutine closein(logical_unit)
        integer, intent(inout) :: logical_unit
        close(logical_unit)
    end

    ! This subroutine reads the header section of the data1 file. This section
    ! consists of a record containing the string 'data1' (to ensure that the file
    ! is indeed a data1 file), a record containing the keystring for the activity
    ! coefficient model for aqueous species to which this data file corresponds,
    ! and the array allocation size variables required to allocate sufficient
    ! array space to store the rest of the data on this data file.
    !
    ! nbta_asv  = the number of basis species on the data file
    ! ncta_asv  = the number of chemical elements on the data file
    ! ntid_asv  = the number of lines in the data file title
    !
    ! ikta_asv  = the maximum number of end-member component species in any solid
    !             solution on the data file
    ! nata_asv  = the number of aqueous species on the data file
    ! ngta_asv  = the number of gas species on the data file
    ! nlta_asv  = the number of pure liquids on the data file
    ! nmta_asv  = the number of pure minerals on the data file
    ! npta_asv  = The number of phases of all types on the data file
    ! nsta_asv  = the number of species of all types on the data file
    ! nxta_asv  = the number of solid-solution phases on the data file
    !
    ! napa_asv  = the number of distinct sets of Pitzer alpha values
    ! nmuta_asv = the number of triplets of ions on the data file for which distinct
    !             Pitzer mu coefficients are defined
    ! nslta_asv = the number of pairs of ions on the data file for which distinct
    !             Pitzer S-lambda coefficients are defined
    !
    ! ipch_asv = the maximum order for pressure corrections to enthalpy functions
    ! ipcv_asv = the maximum order for pressure corrections to volume functions;
    !            the maximum order for pressure corrections to log K and other
    !            Gibbs-energy-based functions is one greater than this
    ! ipbt_asv = the maximum number of Pitzer alpha parameters for any species pair
    ! jpfc_asv = the number of coefficients in the Pitzer parameter temperature
    !            function
    ! narx_asv = maximum number of coefficients per temperature range
    ! ntpr_asv = number of temperature ranges
    subroutine indath(data1, ikta_asv, ipbt_asv, ipch_asv, ipcv_asv, jpfc_asv, &
                      napa_asv, narx_asv, nata_asv, nbta_asv, ncta_asv, ngta_asv, &
                      nlta_asv, nmta_asv, npta_asv, nmuta_asv, nslta_asv, &
                      nsta_asv, ntid_asv, ntpr_asv, nxta_asv, udakey, errno)

        integer, intent(in) :: data1

        integer, intent(out) :: ikta_asv
        integer, intent(out) :: ipbt_asv
        integer, intent(out) :: napa_asv
        integer, intent(out) :: nata_asv
        integer, intent(out) :: nbta_asv
        integer, intent(out) :: ncta_asv
        integer, intent(out) :: ngta_asv
        integer, intent(out) :: nlta_asv
        integer, intent(out) :: nmta_asv
        integer, intent(out) :: npta_asv
        integer, intent(out) :: nmuta_asv
        integer, intent(out) :: nslta_asv
        integer, intent(out) :: nsta_asv
        integer, intent(out) :: ntid_asv
        integer, intent(out) :: nxta_asv
        integer, intent(out) :: ipch_asv
        integer, intent(out) :: ipcv_asv
        integer, intent(out) :: jpfc_asv
        integer, intent(out) :: narx_asv
        integer, intent(out) :: ntpr_asv
        character(len=8), intent(out) :: udakey

        integer, intent(out) :: errno

        ! Local variable declarations.
        character(len=56) ux56
        character(len=8) ux8

        rewind data1

        read (data1) ux8
        if (ux8(1:5) .ne. 'data1') then
            errno = 420
            goto 999
        end if

        read (data1) udakey

        ! Read the array dimension required for chemical elements.
        read (data1) ux56
        read (data1) ncta_asv

        ! Read the array dimension required for basis species.
        read (data1) ux56
        read (data1) nbta_asv

        ! Read the array dimension required for total species.
        read (data1) ux56
        read (data1) nsta_asv

        ! Read the array dimension required for total phases.
        read (data1) ux56
        read (data1) npta_asv

        ! Read the array dimension required for aqueous species.
        read (data1) ux56
        read (data1) nata_asv

        ! Read the array dimension required for pure minerals.
        read (data1) ux56
        read (data1) nmta_asv

        ! Read the array dimension required for pure liquids.
        read (data1) ux56
        read (data1) nlta_asv

        ! Read the array dimension required for gas species.
        read (data1) ux56
        read (data1) ngta_asv

        ! Read the array dimension required for solid-solution phases.
        read (data1) ux56
        read (data1) nxta_asv

        ! Read the array dimension required for solid-solution components
        ! (maximum number per solid solution).
        read (data1) ux56
        read (data1) ikta_asv

        ! Read the array dimension required for the data file title.
        read (data1) ux56
        read (data1) ntid_asv

        ! Read the array dimension required for the temperature ranges in the logK
        ! temperature grid.
        read (data1) ux56
        read (data1) ntpr_asv

        ! Read the array dimension required for the points in a temperature range
        ! on the logK temperature grid.
        read (data1) ux56
        read (data1) narx_asv

        ! Read the array dimension required for the dH/dP order represented on the
        ! data file.
        read (data1) ux56
        read (data1) ipch_asv

        ! Read the array dimension required for the dV/dP order represented on the
        ! data file.
        read (data1) ux56
        read (data1) ipcv_asv

        ! Read the array dimensions for parameters needed for activity coefficient
        ! models.
        if (udakey(1:8) .eq. 'Pitzer  ') then
            ! Read the array dimension required for the sets of Pitzer alpha
            ! coefficients.
            read (data1) ux56
            read (data1) napa_asv

            ! Read the array dimension required for the set of Pitzer S-lambda
            ! coefficients.
            read (data1) ux56
            read (data1) nslta_asv

            ! Read the array dimension required for the set of Pitzer mu
            ! coefficients.
            read (data1) ux56
            read (data1) nmuta_asv

            ! Read the number of coefficients for the Pitzer parameter temperature
            ! function.
            read (data1) ux56
            read (data1) jpfc_asv
        else
            ! Minimum values.
            napa_asv = 1
            nslta_asv = 1
            nmuta_asv = 1
            jpfc_asv = 1
        end if

        ! Set the number of parameters in a Pitzer alpha set.
        if (udakey(1:8) .eq. 'Pitzer  ') then
            ipbt_asv = 2
        else
            ipbt_asv = 1
        end if

        ux8 = ux56(1:8)

        999 continue
    end

    ! This subroutine reads the supporting data file DATA1, starting with its title.
    ! This subroutine should be called after subroutine indath.f has been called to
    ! read the header section (which mostly contains array size allocation data
    ! required to allocate sufficient array space to store the data read by the
    ! present subroutine.
    !
    ! Principal output:
    !
    !   aadh   = array of polynomial coefficients for computing the Debye-Huckel A(gamma,10) parameter
    !   aadhh  = array of polynomial coefficients for computing the Debye-Huckel A(H) parameter
    !   aadhv  = array of polynomial coefficients for computing the Debye-Huckel A(V) parameter
    !   aaphi  = array of polynomial coefficients for computing the Debye-Huckel A(phi) parameter
    !   abdh   = array of polynomial coefficients for computing the Debye-Huckel B parameter
    !   abdhh  = array of polynomial coefficients for computing the Debye-Huckel B(H) parameter
    !   abdhv  = array of polynomial coefficients for computing the Debye-Huckel B(V) parameter
    !   abdot  = array of polynomial coefficients for computing the Helgeson (1969) B-dot parameter
    !   abdoth = array of polynomial coefficients for computing the B-dot(H) parameter
    !   abdotv = array of polynomial coefficients for computing the B-dot(V) parameter
    !   adadhh = array of polynomial coefficients for computing the the pressure derivatives of the Debye-Huckel A(H) parameter
    !   adadhv = array of polynomial coefficients for computing the the pressure derivatives of the Debye-Huckel A(V) parameter
    !   adbdhh = array of polynomial coefficients for computing the the pressure derivatives of the Debye-Huckel B(H) parameter
    !   adbdhv = array of polynomial coefficients for computing the the pressure derivatives of the Debye-Huckel B(V) parameter
    !   adbdth = array of polynomial coefficients for computing the the pressure derivatives of the B-dot(H) parameter
    !   adbdtv = array of polynomial coefficients for computing the the pressure derivatives of the B-dot(V) parameter
    !   adhfsa = array of polynomial coefficients for computing the pressure derivatives of the enthalpy of reaction for reactions read from the data file
    !   adhfe  = array of polynomial coefficients for computing the pressure derivatives of the enthalpy of reaction for the "Eh" reaction
    !   advfe  = array of polynomial coefficients for computing the pressure derivatives of the volume of reaction for the "Eh" reaction
    !   advfsa = array of polynomial coefficients for computing the pressure derivatives of the volume of reaction for reactions read from the data file
    !   amua   = coefficients for calculating Pitzer mu parameters as a function of temperature, read from the data file
    !   aprehw = array of polynomial coefficients for computing the recommended pressure envelope half-width (bars)
    !   apresg = array of polynomial coefficients for computing the pressure (bars) on the 1-atm:steam saturation curve
    !   apxa   = array of interaction coefficients for computing activity coefficients in solid solutions
    !   aslm   = coefficients for calculating Pitzer S-lambda(n) parameters as a function of temperature, read read from the data file
    !   atwta  = array of atomic weights of the elements read from the data file
    !   axhfe  = array of polynomial coefficients for computing the enthalpy of reaction for the "Eh" reaction
    !   axhfsa = array of polynomial coefficients for computing the enthalpy of reaction for reactions read from the data file
    !   axlke  = array of polynomial coefficients for computing the log K for the "Eh" reaction
    !   axlksa = array of polynomial coefficients for computing the log K functions of reactions read from the data file
    !   axvfe  = array of polynomial coefficients for computing the volume of reaction for the "Eh" reaction
    !   axvfsa = array of polynomial coefficients for computing the volume of reaction for reactions read from the data file
    !   azeroa = array of hard core diameters of the species read from the data file
    !   bpxa   = array of site-mixing parameters for computing activity coefficients in solid solutions
    !   cco2   = array of coefficients for computing the activity coefficient of CO2(aq) from the Drummond (1981) equation
    !   cdrsa  = array of reaction coefficients for the reactions read from the data file
    !   cessa  = array of elemental composition coefficients for the species read from the data file
    !   iapxta = array of the numbers of non-zero interaction coefficients for computing activity coefficients in solid solutions
    !   iaqsla = index of the aqueous solution phase, as read from the data file
    !   ibpxta = array of the numbers of non-zero site-mixing paramters for computing activity coefficients in solid solutions
    !   ielam  = flag indicating no use or use of E-lambda terms
    !   igas   = index of the gas phase
    !   insgfa = array of flags for treating the activity coefficients of species that happen to be electrically neutral, as read from the data file
    !   ixrn1a = index of the first non-aqueous solution phase, as read from the data file
    !   ixrn2a = index of the last non-aqueous solution phase, as read from the data file
    !   jpdblo = Pitzer data block organization flag
    !   jptffl = Pitzer parameter temperature function flag
    !   jsola  = array of flags for the activity coefficient models to use for solid solutions, as read from the data file
    !   mwtspa = array of the molecular weights of the species read from the data file
    !   nalpaa = pointer array giving the index of the set of alpha coeffcients for a given set of S-lambda coefficients, as read from the data file
    !   narn1a = start of the range of aqueous species, as read from the data file
    !   narn1a = end of the range of aqueous species, as read from the data file
    !   nbaspa = array of indices of species in basis set, as read from the data file
    !   ncmpra = array giving the start and the end of the range of the species belonging to a given phase, as read from the data file
    !   ndrsa  = array of indices of the species corresponding to the reaction coefficients in the cdrsa array
    !   ndrsra = array giving the start and end of the range in the cdrsa and ndrsa arrays of the species in the reaction which belongs to a given species
    !   nessa  = array of indices of the chemical elements corresponding to the composition coefficients in the cessa array
    !   nessra = array giving the start and end of the range in the cessa and nessa arrays of the chemical elements comprising a given species
    !   ngrn1a = index of the first species in the gas range, as read from the data file
    !   ngrn2a = index of the last species in the gas range, as read from the data file
    !   nlrn1a = index of the first species in the pure liquid range, as read from the data file
    !   nlrn2a = index of the last species in the pure liquid range, as read from the data file
    !   nmrn1a = index of the first species in the pure mineral range, as read from the data file
    !   nmrn2a = index of the last species in the pure mineral range, as read from the data file
    !   nmuta  = the number of species triplets for which mu coefficients are defined, as read from the data file
    !   nmuxa  = indices of species in triplets for which mu coefficients are defined, as read from the data file
    !   nslta  = number of species pairs for which S-lambda coefficients are defined, as read from the data file
    !   nslxa  = indices of species in pairs for which S-lambda coefficients are defined, as read from the data file
    !   nxrn1a = index of the first species in the solid solution range, as read from the data file
    !   nxrn2a = index of the last species in the solid solution range, as read from the data file
    !   palpaa = array of sets of alpha coefficients read from the data file
    !   qclnsa = array of flags indicating if a species was created by cloning
    !   tdamax = the nominal upper temperature limit of the data file
    !   tdamin = the nominal lower temperature limit of the data file
    !   ubasp  = array of names of the species in the basis set
    !   uelema = array of names of the chemical elements read from the data file
    !   uphasa = array of names of phases read from the data file
    !   uptypa = array giving the type of a given phase (e.g., liquid, solid, gas) read from the data file
    !   uspeca = array of names of species read from the data file
    !   utitld = the title read from the data file
    !   vosp0a = array of standard state molar volumes of the species read from the data file
    !   zchara = array of electrical charge numbers of the species read from the data file
    subroutine indata(nad1, aadh, aadhh, aadhv, aaphi, abdh, abdhh, abdhv, abdot, &
                      abdoth, abdotv, adadhh, adadhv, adbdhh, adbdhv, adbdth, &
                      adbdtv, adhfe, adhfsa, advfe, advfsa, amua, aprehw, apresg, &
                      apxa, aslma, atwta, axhfe, axhfsa, axlke, axlksa, axvfe, &
                      axvfsa, azeroa, bpxa, cco2, cdrsa, cessa, iapxa_asv, &
                      iapxta, iaqsla, ibpxa_asv, ibpxta, ielam, igas, ikta_asv, &
                      insgfa, ipbt_asv, ipch, ipch_asv, ipcv, ipcv_asv, ixrn1a, &
                      ixrn2a, jpdblo, jpfc_asv, jptffl, jsola, mwtspa, nalpaa, &
                      napa_asv, napta, narn1a, narn2a, narx_asv, narxt, nata, &
                      nata_asv, nbaspa, nbta, nbta_asv, nbtafd, nbta1_asv, ncmpra, &
                      ncta, ncta_asv, ndrsa, ndrsa_asv, ndrsra, nessa, nessa_asv, &
                      nessra, ngrn1a, ngrn2a, ngta, nlrn1a, nlrn2a, &
                      nlta, nmrn1a, nmrn2a, nmta, nmuta, &
                      nmuta_asv, nmuxa, npta, npta_asv, nslta, nslta_asv, nslxa, &
                      nsta, nsta_asv, ntid_asv, ntitld, ntpr_asv, ntprt, nxrn1a, &
                      nxrn2a, nxta, nxta_asv, qclnsa, palpaa, tdamax, tdamin, &
                      tempcu, ubasp, udakey, udatfi, uelema, uspeca, uphasa, &
                      uptypa, utitld, vosp0a, zchara, errno)
        implicit none

        ! Calling sequence variable declarations.
        integer iapxa_asv,ibpxa_asv,ikta_asv,ipbt_asv,ipch_asv,ipcv_asv
        integer jpfc_asv,napa_asv,narx_asv,nata_asv,nbta_asv,nbta1_asv,ncta_asv
        integer ndrsa_asv,nessa_asv,nmuta_asv
        integer npta_asv,nslta_asv,nsta_asv,ntid_asv,ntpr_asv,nxta_asv

        integer nad1, errno

        integer iapxta(nxta_asv),ibpxta(nxta_asv),insgfa(nata_asv)
        integer jsola(nxta_asv),nalpaa(nslta_asv),narxt(ntpr_asv)
        integer nbaspa(nbta_asv),ncmpra(2,npta_asv),ndrsa(ndrsa_asv)
        integer ndrsra(2,nsta_asv),nessa(nessa_asv),nessra(2,nsta_asv)
        integer nmuxa(3,nmuta_asv),nslxa(2,nslta_asv)

        integer iaqsla,ielam,igas,ipch,ipcv,ixrn1a,ixrn2a,jpdblo,jptffl
        integer napta,narn1a,narn2a,nata,nbta,nbtafd,ncta,ngrn1a,ngrn2a,ngta
        integer nlrn1a,nlrn2a,nlta,nmrn1a,nmrn2a,nmta,nmuta,npta,nslta,nsta
        integer ntitld,ntprt,nxrn1a,nxrn2a,nxta

        logical qclnsa(nsta_asv)

        character(len=8) uelema(ncta_asv)
        character(len=24) uphasa(npta_asv),uptypa(npta_asv)
        character(len=48) ubasp(nbta_asv),uspeca(nsta_asv)
        character(len=80) utitld(ntid_asv)

        character(len=8) udakey,udatfi

        real(8) tempcu(ntpr_asv)

        real(8) aadh(narx_asv,ntpr_asv),aadhh(narx_asv,ntpr_asv)
        real(8) aadhv(narx_asv,ntpr_asv),aaphi(narx_asv,ntpr_asv)
        real(8) abdh(narx_asv,ntpr_asv),abdhh(narx_asv,ntpr_asv)
        real(8) abdhv(narx_asv,ntpr_asv),abdot(narx_asv,ntpr_asv)
        real(8) abdoth(narx_asv,ntpr_asv),abdotv(narx_asv,ntpr_asv)
        real(8) adadhh(narx_asv,ntpr_asv,ipch_asv)
        real(8) adadhv(narx_asv,ntpr_asv,ipcv_asv)
        real(8) adbdhh(narx_asv,ntpr_asv,ipch_asv)
        real(8) adbdhv(narx_asv,ntpr_asv,ipcv_asv)
        real(8) adbdth(narx_asv,ntpr_asv,ipch_asv)
        real(8) adbdtv(narx_asv,ntpr_asv,ipcv_asv)
        real(8) adhfe(narx_asv,ntpr_asv,ipch_asv)
        real(8) advfe(narx_asv,ntpr_asv,ipcv_asv)
        real(8) adhfsa(narx_asv,ntpr_asv,ipch_asv,nsta_asv)
        real(8) advfsa(narx_asv,ntpr_asv,ipcv_asv,nsta_asv)
        real(8) aprehw(narx_asv,ntpr_asv),apresg(narx_asv,ntpr_asv)
        real(8) apxa(iapxa_asv,nxta_asv),atwta(ncta_asv)
        real(8) axhfe(narx_asv,ntpr_asv),axhfsa(narx_asv,ntpr_asv,nsta_asv)
        real(8) axlke(narx_asv,ntpr_asv),axlksa(narx_asv,ntpr_asv,nsta_asv)
        real(8) axvfe(narx_asv,ntpr_asv),axvfsa(narx_asv,ntpr_asv,nsta_asv)

        real(8) amua(jpfc_asv,nmuta_asv)
        real(8) aslma(jpfc_asv,0:ipbt_asv,nslta_asv),azeroa(nata_asv)
        real(8) bpxa(ibpxa_asv,nxta_asv),cco2(5),cdrsa(ndrsa_asv)
        real(8) cessa(nessa_asv),mwtspa(nsta_asv),palpaa(ipbt_asv,napa_asv)
        real(8) vosp0a(nsta_asv),zchara(nsta_asv)

        real(8) tdamax,tdamin

        character(len=24), dimension(:), allocatable :: udrsv
        character(len=8), dimension(:), allocatable :: uessv

        real(8), dimension(:), allocatable :: cdrsv,cessv

        integer ipc,j2,j3,n,nc,ndrsn,nessn,nmax,nn,np,ns,nsc,ntpr,nwatra

        ! integer ilnobl

        logical qx

        character(len=80) ux80
        character(len=56) ux56
        character(len=24) uphasv,uwater,uaqsln,uptsld,uptliq,uptgas,usblkf,ux24
        character(len=8) uendit,usedh,upitz,ustr,ustr2,ustr3,uterm

        data uwater /'H2O                     '/
        data uaqsln /'Aqueous solution        '/
        data uptsld /'Solid                   '/
        data uptliq /'Liquid                  '/
        data uptgas /'Gas                     '/

        data uendit /'endit.  '/,uterm  /'+-------'/
        data usedh  /'SEDH    '/,upitz  /'Pitzer  '/

        ALLOCATE(cessv(ncta_asv))
        ALLOCATE(uessv(ncta_asv))

        ALLOCATE(cdrsv(nbta1_asv))
        ALLOCATE(udrsv(nbta1_asv))

        ! Zero some arrays.
        nmax = nbta_asv
        call initiz(nbaspa,nmax)

        nmax = ndrsa_asv
        call initiz(ndrsa,nmax)
        call initaz(cdrsa,nmax)

        nmax = nsta_asv
        call initaz(vosp0a,nmax)

        nmax = 2*nsta_asv
        call initiz(ndrsra,nmax)

        nmax = narx_asv*ntpr_asv*nsta_asv
        call initaz(axhfsa,nmax)
        call initaz(axlksa,nmax)
        call initaz(axvfsa,nmax)

        nmax = nata_asv
        call initaz(azeroa,nmax)
        call initiz(insgfa,nmax)

        nmax = ipbt_asv*napa_asv
        call initaz(palpaa,nmax)
        nmax = jpfc_asv*(ipbt_asv + 1)*nslta_asv
        call initaz(aslma,nmax)
        nmax = jpfc_asv*nmuta_asv
        call initaz(amua,nmax)

        ! Don't rewind the DATA1 file (nad1). It should be positioned properly by
        ! the preceding call to subroutine indath.f.

        ! Initialize the error counter.
        errno = 0

        ! Set the number of elements on the data file. This equal to the dimensioned
        ! limit. Note that nbta, the number of basis species, is determined in this
        ! subroutine as it is not usually equal to the corresponding dimensioned
        ! limit nbta_asv. In fact, nbta as returned by the subroutine may be
        ! subsequently increased due to "promotions" implied by the contents of the
        ! input file.

        ncta = ncta_asv

        ! Read the data file title.
        ntitld = 0
        do n = 1,ntid_asv
            read (nad1) utitld(n)
            ntitld = ntitld + 1
            if (utitld(n)(1:8) .eq. uterm(1:8)) go to 140
        end do
        140 continue

        ! Write the first 5 lines of the data file title to the screen file.
        nn = min(ntitld,5)
        do n = 1,nn
            if (utitld(n)(1:8) .eq. uterm(1:8)) go to 150
            j2 = ilnobl(utitld(n))
            j2 = min(j2,74)
        end do
        150 continue

        ! Write the complete data file title, less terminator, if any, to the output
        ! file.
        do n = 1,ntitld
            if (utitld(n)(1:8) .eq. uterm(1:8)) go to 160
            j2 = ilnobl(utitld(n))
            j2 = min(j2,74)
        end do
        160 continue

        ! Search the data file title for the usual identifying three-letter
        ! keystring (e.g., com, hmw, etc.).
        udatfi = 'current'
        do n = 1,ntitld
            ux80 = utitld(n)
            call lejust(ux80)
            if (ux80(1:6) .eq. 'data0.') then
                udatfi = ux80(7:9)
                go to 170
            end if
        end do
        170 continue

        ! Read the actual number of temperature ranges in the temperature grid.
        read (nad1) ux56
        read (nad1) ntprt

        ! Read the actual number of coefficients in each range.
        do ntpr = 1,ntprt
            read (nad1) ux56
            read (nad1) narxt(ntpr)
        end do

        ! Read a flag indicating the degree of representation of enthalpy functions.
        read (nad1) ux56
        read (nad1) ipch

        ! Read a flag indicating the degree of representation of volume functions.
        read (nad1) ux56
        read (nad1) ipcv

        if (udakey(1:8) .eq. upitz(1:8)) then
            ! Read the Pitzer data block organization flag.
            read (nad1) ux56
            read (nad1) jpdblo

            ! Read the Pitzer parameter temperature function flag.
            read (nad1) ux56
            read (nad1) jptffl
        end if

        ! Read chemical elements data.
        read (nad1) ux24

        do nc = 1,ncta
            read (nad1) uelema(nc),atwta(nc)
        end do

        ! Read nominal temperature limits (Celsius) for the data file.
        read (nad1) ux56
        read (nad1) tdamin,tdamax

        ! Read the maximum temperatures (tempcu) of the temperature ranges. These
        ! are used to find the temperature range flag (ntpr) for any specified
        ! temperature (see EQLIB/gntpr.f).
        read (nad1) ux56
        do n = 1,ntprt
            read (nad1) tempcu(n)
        end do

        ! Read interpolating polynomial coefficients for computing the standard grid
        ! pressure (bars) as a function of temperature (Celsius). Often this grid
        ! corresponds to 1.013 bar up to 100C and the steam-liquid water saturation
        ! pressure at higher temperatures.
        !
        ! Calling sequence substitutions:
        !   apresg for arr
        call indatc(nad1,apresg,narx_asv,narxt,ntpr_asv,ntprt,ux24)

        if (ipcv .ge. 0) then
            ! Read interpolating polynomial coefficients for computing the
            ! recommended pressure envelope half width (bars).
            !
            ! Calling sequence substitutions:
            !   aprehw for arr
            call indatc(nad1,aprehw,narx_asv,narxt,ntpr_asv,ntprt,ux24)
        end if

        if (udakey(1:8) .eq. usedh(1:8)) then
            ! The aqeuous species activity coefficient formalism is consistent with
            ! the B-dot equation, the Davies equation, or similar equations.

            ! Read interpolating polynomial coefficients for the Debye-Huckel
            ! A(gamma,10) parameter and related parameters.
            !
            ! Calling sequence substitutions:
            !   aadh for arr
            call indatc(nad1,aadh,narx_asv,narxt,ntpr_asv,ntprt,ux24)

            if (ipch .ge. 0) then
                ! Calling sequence substitutions:
                !   aadhh for arr
                call indatc(nad1,aadhh,narx_asv,narxt,ntpr_asv,ntprt,ux24)

                do ipc = 1,ipch
                    ! Calling sequence substitutions:
                    !   adadhh for arr
                    !   ipch_asv for ipcx_asv
                    call indatd(nad1,adadhh,ipc,ipch_asv,narxt,narx_asv,ntprt, &
                                ntpr_asv,ux24)
                end do
            end if

            if (ipcv .ge. 0) then
                ! Calling sequence substitutions:
                !   aadhv for arr
                call indatc(nad1,aadhv,narx_asv,narxt,ntpr_asv,ntprt,ux24)

                do ipc = 1,ipcv
                    ! Calling sequence substitutions:
                    !   adadhv for arr
                    !   ipcv_asv for ipcx_asv
                    call indatd(nad1,adadhv,ipc,ipcv_asv,narxt,narx_asv,ntprt, &
                                ntpr_asv,ux24)
                end do
            end if

            ! Read interpolating polynomial coefficients for the Debye-Huckel
            ! B(gamma) and related parameters.
            ! Calling sequence substitutions:
            !   abdh for arr
            call indatc(nad1,abdh,narx_asv,narxt,ntpr_asv,ntprt,ux24)

            if (ipch .ge. 0) then
                ! Calling sequence substitutions:
                !   abdhh for arr
                call indatc(nad1,abdhh,narx_asv,narxt,ntpr_asv,ntprt,ux24)

                do ipc = 1,ipch
                    ! Calling sequence substitutions:
                    !   adbdhh for arr
                    !   ipch_asv for ipcx_asv
 
                    call indatd(nad1,adbdhh,ipc,ipch_asv,narxt,narx_asv,ntprt, &
                                ntpr_asv,ux24)
                end do
            end if

            if (ipcv .ge. 0) then
                ! Calling sequence substitutions:
                !   abdhv for arr
                call indatc(nad1,abdhv,narx_asv,narxt,ntpr_asv,ntprt,ux24)

                do ipc = 1,ipcv
                    ! Calling sequence substitutions:
                    !   adbdhv for arr
                    !   ipcv_asv for ipcx_asv
                    call indatd(nad1,adbdhv,ipc,ipcv_asv,narxt,narx_asv,ntprt, &
                                ntpr_asv,ux24)
                end do
            end if

            ! Read interpolating polynomial coefficients for the B-dot parameter and
            ! related parameters.
            !
            ! Calling sequence substitutions:
            !   abdot for arr
            call indatc(nad1,abdot,narx_asv,narxt,ntpr_asv,ntprt,ux24)

            if (ipch .ge. 0) then
                ! Calling sequence substitutions:
                !   abdoth for arr
                call indatc(nad1,abdoth,narx_asv,narxt,ntpr_asv,ntprt,ux24)

                do ipc = 1,ipch
                    ! Calling sequence substitutions:
                    !   adbdth for arr
                    !   ipch_asv for ipcx_asv
                    call indatd(nad1,adbdth,ipc,ipch_asv,narxt,narx_asv,ntprt, &
                                ntpr_asv,ux24)
                end do
            end if

            if (ipcv .ge. 0) then
                ! Calling sequence substitutions:
                !   abdotv for arr
                call indatc(nad1,abdotv,narx_asv,narxt,ntpr_asv,ntprt,ux24)

                do ipc = 1,ipcv
                    ! Calling sequence substitutions:
                    !   adbdtv for arr
                    !   ipcv_asv for ipcx_asv
                    call indatd(nad1,adbdtv,ipc,ipcv_asv,narxt,narx_asv,ntprt, &
                                ntpr_asv,ux24)
                end do
            end if

            ! Read coefficients for the Drummond (1981) equation. This equation
            ! represents the activity coeficient of CO2(aq) as a function of
            ! temperature and ionic strength in sodium chloride solutions.
            read (nad1) ux24
            read (nad1) (cco2(n), n = 1,5)
        end if

        if (udakey(1:8) .eq. upitz(1:8)) then
            ! The aqeuous species activity coefficient formalism is consistent with
            ! Pitzer's equations. Read interpolating polynomial coefficients for
            ! Debye-Huckel A(phi) and related parameters.
            !
            ! Calling sequence substitutions:
            !   aaphi for arr
            call indatc(nad1,aaphi,narx_asv,narxt,ntpr_asv,ntprt,ux24)

            if (ipch .ge. 0) then
                ! Calling sequence substitutions:
                !   aadhh for arr
                call indatc(nad1,aadhh,narx_asv,narxt,ntpr_asv,ntprt,ux24)

                do ipc = 1,ipch
                    ! Calling sequence substitutions:
                    !   adadhh for arr
                    !   ipch_asv for ipcx_asv
                    call indatd(nad1,adadhh,ipc,ipch_asv,narxt,narx_asv,ntprt,&
                                ntpr_asv,ux24)
                end do
            end if

            if (ipcv .ge. 0) then
                ! Calling sequence substitutions:
                !   aadhv for arr
                call indatc(nad1,aadhv,narx_asv,narxt,ntpr_asv,ntprt,ux24)

                do ipc = 1,ipcv
                    ! Calling sequence substitutions:
                    !   adadhv for arr
                    !   ipcv_asv for ipcx_asv
                    call indatd(nad1,adadhv,ipc,ipcv_asv,narxt,narx_asv,ntprt,&
                                ntpr_asv,ux24)
                end do
            end if
        end if

        ! Read interpolating polynomial coefficients for the log K of the "Eh"
        ! reaction:
        !
        !   2 H2O(l) = 2 O2(g) + 4 H+ + 4 e-
        !
        ! Calling sequence substitutions:
        !   axlke for arr
        call indatc(nad1,axlke,narx_asv,narxt,ntpr_asv,ntprt,ux24)

        if (ipch .ge. 0) then
            ! Calling sequence substitutions:
            !   axhfe for arr
            call indatc(nad1,axhfe,narx_asv,narxt,ntpr_asv,ntprt,ux24)

            do ipc = 1,ipch
                ! Calling sequence substitutions:
                !   adhfe for arr
                !   ipch_asv for ipcx_asv
                call indatd(nad1,adhfe,ipc,ipch_asv,narxt,narx_asv,ntprt,&
                            ntpr_asv,ux24)
            end do
        end if

        if (ipcv .ge. 0) then
            ! Calling sequence substitutions:
            !   axvfe for arr
            call indatc(nad1,axvfe,narx_asv,narxt,ntpr_asv,ntprt,ux24)

            do ipc = 1,ipcv
                ! Calling sequence substitutions:
                !   advfe for arr
                !   ipcv_asv for ipcx_asv
                call indatd(nad1,advfe,ipc,ipcv_asv,narxt,narx_asv,ntprt,&
                            ntpr_asv,ux24)
            end do
        end if

        ! Read the phases and species and assocated data from the data file. The
        ! following variables are used as counters:
        !
        !  np     = phase index
        !  ns     = species index

        ! Initialize the qclnsa array to .false.
        qx = .false.
        call initlv(qclnsa,nsta_asv,qx)

        ! Initialize the following variables, all of which are used below as
        ! counters.
        !
        !   nessn  = counter for the cessa and nessa arrays
        !   ndrsn  = counter for the cdrsa and ndrsa arrays
        !   ns     = species index
        !   nbta   = number of basis species
        !   nata   = number of aqueous species
        !   ngta   = number of gas species
        !   nmta   = number of pure mineral species
        !   nlta   = number of pure liquid species
        !   nxta   = number of solid solution phases

        nessn = 0
        ndrsn = 0
        ns = 0
        nbta = 0
        nata = 0
        ngta = 0
        nmta = 0
        nlta = 0
        nxta = 0

        ! Process the aqueous species superblock. Set up the aqueous solution as the
        ! first phase.
        np = 1
        uphasv(1:24) = uaqsln(1:24)
        iaqsla = np
        uphasa(np)(1:24) = uphasv(1:24)
        uptypa(np)(1:24) = uaqsln(1:24)
        usblkf(1:24) = uaqsln(1:24)
        ncmpra(1,1) = 1
        narn1a = 1

        ! Read the superblock header.
        read (nad1) ustr,ustr2,ustr3

        ! Read the blocks in the current superblock.
        call indats(adhfsa, advfsa, axhfsa, axlksa, axvfsa, cdrsa, cdrsv, cessa, &
                    cessv, ipch, ipch_asv, ipcv, ipcv_asv, mwtspa, nad1, narxt, &
                    narx_asv, nata, nbta, nbta_asv, nbta1_asv, nbtafd, &
                    ncmpra, ncta, ncta_asv, ndrsa, ndrsa_asv, ndrsn, ndrsra, &
                    errno, nessa, nessa_asv, nessn, nessra, ngta, nlta, &
                    nmta, np, npta_asv, ns, nsta_asv, ntprt, &
                    ntpr_asv, uaqsln, ubasp, udrsv, uelema, uendit, uessv, uphasa, &
                    uphasv, uptgas, uptliq, uptsld, uptypa, usblkf, uspeca, &
                    vosp0a, zchara)

        ncmpra(2,np) = ns
        narn2a = ns

        ! Check to see that water is the first species in the phase "aqueous
        ! solution". This is required so that all solute species can be cleanly
        ! referenced in simple loop; that is, in a loop of the form
        ! "do ns = narn1a + 1,narn2a".
        nwatra = 0
        if (uspeca(narn1a)(1:24) .eq. uwater(1:24)) nwatra = 1

        if (nwatra .eq. 0) then
            j3 = ilnobl(uwater)
            errno = 1
            ! 1150   format(/' * Error - (EQLIB/indata) The species ',
            !     $  /7x,a,' (',a,') must be listed on the',
            !     $  /7x,'data file as the first species in its phase.')
            !        go to 999
        end if

        ! Process the pure minerals superblock. Each pure mineral is both a species
        ! and a phase. The phase name variable uphasv will be set to the name of
        ! each mineral as its block is read.
        usblkf(1:24) = uptsld(1:24)
        nmrn1a = ns + 1

        ! Read the superblock header.
        read (nad1) ustr,ustr2,ustr3

        ! Read the blocks in the current superblock.
        call indats(adhfsa, advfsa, axhfsa, axlksa, axvfsa, cdrsa, cdrsv, cessa, &
                    cessv, ipch, ipch_asv, ipcv, ipcv_asv, mwtspa, nad1, narxt, &
                    narx_asv, nata, nbta, nbta_asv, nbta1_asv, nbtafd, &
                    ncmpra, ncta, ncta_asv, ndrsa, ndrsa_asv, ndrsn, ndrsra, &
                    errno, nessa, nessa_asv, nessn, nessra, ngta, nlta, &
                    nmta, np, npta_asv, ns, nsta_asv, ntprt, &
                    ntpr_asv, uaqsln, ubasp, udrsv, uelema, uendit, uessv, uphasa, &
                    uphasv, uptgas, uptliq, uptsld, uptypa, usblkf, uspeca, &
                    vosp0a, zchara)

        nmrn2a = ns
        if (nmrn2a .le. narn2a) nmrn1a = 0

        ! There is presently no superblock corresponding to pure liquids. Set up
        ! water as a pure liquid.
        usblkf(1:24) = uptliq(1:24)
        nlrn1a = 0
        nlrn2a = 0
        nlta = 0

        if (nwatra .gt. 0) then
            np = np + 1
            ns = ns + 1
            uphasv(1:24) = uspeca(nwatra)(1:24)
            uphasa(np)(1:24) = uphasv(1:24)
            uptypa(np)(1:24) = uptliq(1:24)
            ncmpra(1,np) = ns
            ncmpra(2,np) = ns
            nsc = 1
            call clones(axlksa, cdrsa, cessa, mwtspa, narx_asv, ndrsa, ndrsa_asv, &
                        ndrsn, ndrsra, nessa, nessa_asv, nessn, nessra, np, &
                        npta_asv, ns, nsc, nsta_asv, ntpr_asv, uphasa, uspeca, &
                        zchara)
            qclnsa(ns) = .true.
            nlrn1a = ns
            nlrn2a = ns
            nlta = 1
        end if

        ! Process the gas species superblock. Set up the gas phase as the next
        ! phase.
        uphasv(1:24) = uptgas(1:24)
        usblkf(1:24) = uptgas(1:24)
        np = np + 1
        igas = np
        uphasa(np)(1:24) = uphasv(1:24)
        uptypa(np)(1:24) = uptgas(1:24)
        ncmpra(1,np) = ns + 1
        ngrn1a = ns + 1

        ! Read the superblock header.
        read (nad1) ustr,ustr2,ustr3

        ! Read the blocks in the current superblock.
        call indats(adhfsa, advfsa, axhfsa, axlksa, axvfsa, cdrsa, cdrsv, cessa, &
                    cessv, ipch, ipch_asv, ipcv, ipcv_asv, mwtspa, nad1, narxt, &
                    narx_asv, nata, nbta, nbta_asv, nbta1_asv, nbtafd, &
                    ncmpra, ncta, ncta_asv, ndrsa, ndrsa_asv, ndrsn, ndrsra, &
                    errno, nessa, nessa_asv, nessn, nessra, ngta, nlta, &
                    nmta, np, npta_asv, ns, nsta_asv, ntprt, &
                    ntpr_asv, uaqsln, ubasp, udrsv, uelema, uendit, uessv, uphasa, &
                    uphasv, uptgas, uptliq, uptsld, uptypa, usblkf, uspeca, &
                    vosp0a, zchara)

        ngrn2a = ns
        if (ngrn2a .le. nlrn2a) ngrn1a = 0
        ncmpra(2,np) = ns

        ! Process the solid solution superblock.
        read (nad1) ustr,ustr2,ustr3
        nxrn1a = ns + 1
        ixrn1a = np + 1

        call indatp(apxa, axlksa, bpxa, cdrsa, cessa, iapxa_asv, iapxta, &
                    ibpxa_asv, ibpxta, ikta_asv, jsola, mwtspa, nad1, narx_asv, &
                    ncmpra, ndrsa, ndrsa_asv, ndrsn, ndrsra, errno, nessa, &
                    nessa_asv, nessn, nessra, nmrn1a, nmrn2a, np, npta_asv, ns, &
                    nsta_asv, ntpr_asv, nxta, nxta_asv, qclnsa, uendit, uspeca, &
                    uphasa, uptsld, uptypa, zchara)

        npta = np
        nsta = ns
        nxrn2a = ns
        ixrn2a = np
        if (nxrn2a .le. nlrn2a) then
            nxrn1a = 0
            nxrn2a = 0
            ixrn1a = 0
            ixrn2a = 0
        end if

        ! Set up the nbaspa array and expand the elements of the ubasp array to the
        ! full 48 characters. Convert basis species indices in the ndrsa array to
        ! species indices.
        call dfbasp(nbaspa, nbta, nbta_asv, ndrsa, ndrsa_asv, ndrsra, errno, nsta, &
                    nsta_asv, ubasp, uspeca)

        if (udakey(1:8) .eq. usedh(1:8)) then
            ! The aqeuous species activity coefficient formalism is consistent with
            ! the B-dot equation, the Davies equation, or similar equations. Read
            ! the appropriate data for this formalism.
            call inbdot(azeroa, insgfa, nad1, narn1a, narn2a, nata, nata_asv, &
                        errno, nsta_asv, uspeca)
        end if

        if (udakey(1:8) .eq. upitz(1:8)) then
            ! The aqeuous species activity coefficient formalism is consistent with
            ! Pitzer's equations. Read the appropriate data for this formalism.
            call inupt(amua, aslma, ielam, ipbt_asv, jpdblo, jpfc_asv, nad1, &
                       nalpaa, napa_asv, napta, narn1a, narn2a, errno, nmuta, &
                       nmuta_asv, nmuxa, nslta, nslta_asv, nslxa, nsta_asv, &
                       palpaa, uspeca, zchara)
        end if

        ! The following is a bit of nonsense so compiler warnings will not be 
        ! generated saying that ux80, ustr, ustr2, and ustr3 are not used (they are
        ! all used to read unused data).
        ux80(1:56) = ux56
        ustr3 = ux80(1:8)
        ustr = ustr2
        ustr2 = ustr3
        ustr3 = ustr

        DEALLOCATE(cessv)
        DEALLOCATE(uessv)
        DEALLOCATE(cdrsv)
        DEALLOCATE(udrsv)
    end

    ! This subroutine reads from the data file the block of individual species
    ! parameters for the B-dot model of aqueous species activity coefficients. For
    ! each solute species, these parameters are its hard core diameter (azeroa) and
    ! its neutral species flag (insgfa). The latter is relevant only for
    ! electrically neutral species. If it is has a value of 0, the log activity
    ! coefficient is set to zero; if it has a value of -1, the log activity
    ! coefficient is represented by the Drummond (1981) polynomial. Water (the
    ! solvent) is not subject to control by the insgfa flag.
    subroutine inbdot(azeroa,insgfa,nad1,narn1a,narn2a,nata,nata_asv,nerr,nsta_asv,uspeca)
        implicit none

        integer nata_asv,nsta_asv

        integer insgfa(nata_asv)
        integer nad1,narn1a,narn2a,nata,nerr

        character*48 uspeca(nsta_asv)

        real*8 azeroa(nata_asv)

        integer igx,j2,na,naz,ncount,ns

        ! integer ilnobl

        real*8 azdef,azx

        character*24 unam,unam1,unam2
        character*8 uendit

        data uendit /'endit.  '/

        ! The following variable is the default value for the hard core diameter of
        ! an aqueous solute species. Note that hard core diameters are given in
        ! units of 10**-8 cm.

        data azdef  /4.0/

        ! Initialize the azeroa and insgfa arrays to zero.
        do na = 1,nata_asv
            azeroa(na) = 0.
            insgfa(na) = 0
        end do

        ! Read the block contents.
        naz = 0

        ! Read the species name and azeroa and insgfa data.
        110 read (nad1) unam,azx,igx

        ! Test for the end of the data block.
        if (unam(1:8) .eq. uendit(1:8)) go to 120
            ! Find the species index, ns.
            ! Calling sequence substitutions:
            !     narn1a for nrn1a
            !     narn2a for nrn2a
            call srchn(narn1a,narn2a,ns,nsta_asv,unam,uspeca)

            ! If not found among the loaded species, skip.
            if (ns .le. 0) then
                j2 = ilnobl(unam)
         !        write (noutpt,1020) unam(1:j2)
         !        write (nttyo,1020) unam(1:j2)
         ! 1020   format(/' * Warning - (EQLIB/inbdot) Have B-dot model',
         !     $  ' parameters listed',/7x,'for an aqueous species named ',a,
         !     $  ', but there is',/7x,'no data block for such a species.')
                go to 110
        end if

        ! Compute the aqueous species index na.
        na = ns - narn1a + 1

        ! Test for duplicate input.

        if (azeroa(na) .gt. 0.) then
     !        write (noutpt,1030) unam(1:j2),azx,igx,azeroa(na),insgfa(na)
     !        write (nttyo,1030) unam(1:j2),azx,igx,azeroa(na),insgfa(na)
     ! 1030   format(/' * Warning - (EQLIB/inbdot) Have a duplicate entry',
     !     $  ' on the data file for',/7x,'the B-dot model parameters of',
     !     $  ' the species ',a,'.',/7x,'The duplicate entry values are:',
     !     $  //9x,'azero= ',f7.2,', insgf= ',i3,
     !     $  //7x,'The first entry values are:',
     !     $  //9x,'azero= ',f7.2,', insgf= ',i3,
     !     $  //7x,'The first entry values will be used.')
            go to 110
        end if

        naz = naz + 1
        if (naz .gt. nata) then
     !        write (noutpt,1040) nata
     !        write (nttyo,1040) nata
     ! 1040   format(/' * Error - (EQLIB/inbdot) There are more entries',
     !     $  /7x,'for species with  B-dot model parameters than there are',
     !     $  /7x,'aqueous species, which number ',i4,'.')
            nerr = nerr + 1
            go to 999
        end if

        azeroa(na) = azx
        insgfa(na) = igx
        go to 110

        ! Check for solute species with no entries.
        120 do na = 1,nata
            if (azeroa(na) .le. 0.) go to 140
        end do
        go to 999

        ! Assign the default value if needed.

        ! 140 write (noutpt,1050) azdef
        ! 1050 format(/' * Note - (EQLIB/inbdot) The following aqueous species',
        !     $ ' have been assigned',/7x,'a default hard core diameter of',
        !     $ ' ',f6.3,' x 10**-8 cm:',/)
        140 continue
        ncount = 0
        do ns = narn1a,narn2a
            na = ns - narn1a + 1
            if (azeroa(na) .le. 0.) then
                azeroa(na) = azdef
                if (ns .ne. narn1a) then
                    if (ncount .le. 0) then
                        unam1 = uspeca(ns)(1:24)
                        ncount = 1
                    else
                        unam2 = uspeca(ns)(1:24)
                        j2 = ilnobl(unam2)
                        ! write (noutpt,1060) unam1,unam2(1:j2)
                        ! 1060 format(9x,a24,3x,a)
                        ncount = 0
                    end if
                end if
            end if
        end do

        if (ncount .eq. 1) then
            j2 = ilnobl(unam1)
            ! write (noutpt,1070) unam1(1:j2)
            ! 1070 format(9x,a)
        end if
        999 continue
    end

    subroutine initaz(array, nmax)
        implicit none

        integer, intent(in) :: nmax
        real*8, intent(inout) :: array(nmax)

        integer i

        do i = 1,nmax
            array(i) = 0.0
        end do
    end

    subroutine initiz(iarray, nmax)
        implicit none

        integer, intent(in) :: nmax
        integer, intent(inout) :: iarray(nmax)

        integer i

        do i = 1,nmax
            iarray(i) = 0
        end do
    end

    ! This subroutine initializes the logical array qarray to qvalue over the
    ! first nmax positions. Normally, nmax would be the dimension of the 1D qarray.
    ! However, nmax could be less than the true dimension. Also, qarray could
    ! actually have more than one dimension. For example, if the array is really
    ! qa, having dimensions of i1 and i2, this subroutine could be used by calling
    ! it in the following manner: call initlv(qa,(i1*i2),qvalue). Use this
    ! subroutine with caution if nmax is not the product of the true (declared)
    ! dimensions.
    subroutine initlv(qarray,nmax,qvalue)
        implicit none

        integer nmax

        logical qarray(nmax),qvalue

        integer i,ileft
 
        logical qv

        qv = qvalue
        ileft = (nmax/8)*8
 
        do i = 1,ileft,8
            qarray(i) = qv
            qarray(i + 1) = qv
            qarray(i + 2) = qv
            qarray(i + 3) = qv
            qarray(i + 4) = qv
            qarray(i + 5) = qv
            qarray(i + 6) = qv
            qarray(i + 7) = qv
        end do

        do i = ileft + 1,nmax
            qarray(i) = qv
        end do
    end

    integer function ilnobl(ustr)
        implicit none

        character*(*), intent(in) :: ustr

        integer j, nchars

        nchars = len(ustr)
        ilnobl = 0

        do j = nchars,1,-1
            if (ustr(j:j) .ne. ' ') then
                ilnobl = j
                go to 999
            end if
        end  do

        999 continue
    end

    ! This subroutine finds the position of the first non-blank character in the
    ! string ustr.
    integer function ifnobl(ustr)
        implicit none

        character*(*) ustr
        integer j, nchars

        nchars = len(ustr)
        ifnobl = 0

        do j = 1, nchars
            if (ustr(j:j) .ne. ' ') then
                ifnobl = j
                go to 999
            end if
        end do

        999 continue
    end

    subroutine lejust(ustr)
        implicit none

        character*(*), intent(inout) :: ustr

        integer j, jj, jbl, j1, nchars
        ! integer ifnobl

        nchars = len(ustr)
        j1 = ifnobl(ustr)
        jbl = j1 - 1

        if (jbl .gt. 0) then
            do jj = j1, nchars
                j = jj - jbl
                ustr(j:j) = ustr(jj:jj)
            end do
            do j = nchars - jbl + 1, nchars
                ustr(j:j) = ' '
            end do
        end if
    end

    ! This subroutine reads the solid solution superblock from the supporting data
    ! file "data1".
    subroutine indatp(apxa, axlksa, bpxa, cdrsa, cessa, iapxa_asv, iapxta, &
                      ibpxa_asv, ibpxta, ikta_asv, jsola, mwtspa, nad1, narx_asv, &
                      ncmpra, ndrsa, ndrsa_asv, ndrsn, ndrsra, nerr, nessa, &
                      nessa_asv, nessn, nessra, nmrn1a, nmrn2a, np, &
                      npta_asv, ns, nsta_asv, ntpr_asv, nxta, nxta_asv, &
                      qclnsa, uendit, uspeca, uphasa, uptsld, uptypa, zchara)
        implicit none

        integer iapxa_asv,ibpxa_asv,ikta_asv,narx_asv,ndrsa_asv,nessa_asv
        integer npta_asv,nsta_asv,ntpr_asv,nxta_asv
        integer iapxta(nxta_asv),ibpxta(nxta_asv),jsola(nxta_asv)
        integer ncmpra(2,npta_asv),ndrsa(ndrsa_asv),ndrsra(2,nsta_asv)
        integer nessa(nessa_asv),nessra(2,nsta_asv)
        integer nad1,ndrsn,nerr,nessn,nmrn1a,nmrn2a,np,ns,nxta
        logical qclnsa(nsta_asv)
        character*24 uphasa(npta_asv),uptypa(npta_asv)
        character*24 uptsld
        character*48 uspeca(nsta_asv)
        character*8 uendit
        real*8 apxa(iapxa_asv,nxta_asv)
        real*8 axlksa(narx_asv,ntpr_asv,nsta_asv)
        real*8 bpxa(ibpxa_asv,nxta_asv),cdrsa(ndrsa_asv),cessa(nessa_asv)
        real*8 mwtspa(nsta_asv),zchara(nsta_asv)
        integer j2,j3,jsolv,n,ncmptv,nsc,nx

        ! integer ilnobl

        character*24 uphasv
        character(len=24), dimension(:), allocatable :: ucompv

        ALLOCATE(ucompv(ikta_asv))

        ! The label below defines a loop for reading the blocks in the superblock.

        100 continue

        ! Read a species block.
        read (nad1) uphasv,ncmptv,jsolv
        j3 = ilnobl(uphasv)

        ! Check for end of this current superblock.
        if (uphasv(1:8) .eq. uendit(1:8)) go to 200
        np = np + 1
        uphasa(np) = uphasv
        uptypa(np) = uptsld

        nxta = nxta + 1
        nx = nxta
        jsola(nx) = jsolv

        if (ncmptv .gt. 0) then
            ! Read the names of component species.
            read (nad1) (ucompv(n), n = 1,ncmptv)
        else
            nerr = nerr + 1
     !        write (noutpt,1020) uphasv(1:j3)
     !        write (noutpt,1020) uphasv(1:j3)
     ! 1020   format(/' * Error - (EQLIB/indatp) The solid solution ',a,
     !     $  /7x,'has no components specified on the data file.')
        end if

        ! Read the activity coefficient parameters, first the ordinary parameters
        ! (apx), then the site-mixing parameters (bpx).
        read (nad1) iapxta(nx)
        if (iapxta(nx) .gt. 0) read (nad1) (apxa(n,nx), n = 1,iapxta(nx))
        read (nad1) ibpxta(nx)
        if (ibpxta(nx) .gt. 0) read (nad1) (bpxa(n,nx), n = 1,ibpxta(nx))

        ! Clone the component species.
        ncmpra(1,np) = ns + 1
        ncmpra(2,np) = ns + ncmptv
        do n = 1,ncmptv
            ns = ns + 1
            do nsc = nmrn1a,nmrn2a
                if (ucompv(n)(1:24) .eq. uspeca(nsc)(1:24)) then
                    call clones(axlksa, cdrsa, cessa, mwtspa, narx_asv, ndrsa, &
                                ndrsa_asv, ndrsn, ndrsra, nessa, nessa_asv, nessn, &
                                nessra, np, npta_asv, ns, nsc, nsta_asv, ntpr_asv, &
                                uphasa, uspeca, zchara)
                    qclnsa(ns) = .true.
                    go to 130
                end if
            end do

            ! The listed component was not found as a pure mineral species.
            j2 = ilnobl(ucompv(n))
            !        write (noutpt,1040) ucompv(n)(1:j2),uphasv(1:j3)
            !        write (nttyo,1040) ucompv(n)(1:j2),uphasv(1:j3)
            ! 1040   format(/" * Error - (EQLIB/indatp) Couldn't find the pure",
            !     $  ' phase equivalent',/7x,'of the species',/7x,a,' (',a,'),',
            !     $  ' therefore',/7x,'could not create it by cloning.')
            nerr = nerr + 1
            130 continue
        end do

        ! Loop back to read another species block.
        go to 100

        200 DEALLOCATE(ucompv)
    end

    ! This subroutine matches the species name unam with the corresponding entry in
    ! the nrn1a-th through nrn2a-th range of the species name array uspeca. Only the
    ! first 24 characters are compared (uspeca has 48 characters, unam only 24).
    ! This subroutine returns the species index ns. If there is no match, ns is
    ! returned with a value of 0.
    subroutine srchn(nrn1a, nrn2a, ns, nstmax, unam, uspeca)
        implicit none

        integer nstmax
        integer nrn1a,nrn2a,ns
        character*48 uspeca(nstmax)
        character*24 unam

        do ns = nrn1a, nrn2a
            if (uspeca(ns)(1:24) .eq. unam(1:24)) go to 999
        end do

        ns = 0

        999 continue
    end

    ! This subroutine reads the parameters for Pitzer's equations from the data
    ! file.
    !
    !
    ! Principal output:
    ! amua   = coefficients for calculating Pitzer mu parameters as a function of
    !          temperature
    ! aslma  = coefficients for calculating Pitzer S-lambda(n) parameters as a
    !          function of temperature
    ! nalpaa = pointer array giving the index of the set of alpha coeffcients for a
    !          given set of S-lambda coefficients
    ! nmuta  = number of species triplets for which mu coefficients are defined
    ! nmuxa  = indices of species in triplets for which mu coefficients are defined
    ! nslta  = number of species pairs for which S-lambda coefficients are defined
    ! nslxa  = indices of species in pairs for which S-lambda coefficients are
    !          defined
    ! palpaa = array of sets of alpha coefficients
    subroutine inupt(amua, aslma, ielam, ipbt_asv, jpdblo, jpfc_asv, nad1, &
                     nalpaa, napa_asv, napta, narn1a, narn2a, nerr, nmuta, &
                     nmuta_asv, nmuxa, nslta, nslta_asv, nslxa, nsta_asv, palpaa, &
                     uspeca, zchara)
        implicit none
        integer ipbt_asv,jpfc_asv,napa_asv,nmuta_asv,nslta_asv,nsta_asv

        integer nalpaa(nslta_asv),nmuxa(3,nmuta_asv),nslxa(2,nslta_asv)

        integer ielam,jpdblo,nad1,napta,narn1a,narn2a,nerr,nmuta,nslta

        character(len=48) uspeca(nsta_asv)

        real(8) amua(jpfc_asv,nmuta_asv)
        real(8) aslma(jpfc_asv,0:ipbt_asv,nslta_asv)
        real(8) palpaa(ipbt_asv,napa_asv)
        real(8) zchara(nsta_asv)

        integer i, j, ja, j2, nblock, nmu, ns, nsl

        ! integer ilnobl

        logical qx

        character(len=80) uline
        character(len=24) unam1,unam2,unam3
        character(len=16) ux16
        character(len=8) uelam,uendit,ux8

        real(8) aax,z1,z2

        real(8), dimension(:), allocatable :: alphai

        data uendit /'endit.  '/

        ALLOCATE(alphai(ipbt_asv))

        if (jpdblo .eq. -1) then
            if (ipbt_asv .ne. 2) then
                write (ux8,'(i5)') ipbt_asv
                call lejust(ux8)
                j2 = ilnobl(ux8)
                !          write (noutpt,1000) ux8(1:j2)
                !          write (nttyo,1000) ux8(1:j2)
                ! 1000     format(/' * Error - (EQLIB/inupt) Have an illegal value',
                !     $    ' of ',a,' for the array',/7x,'allocation size variable',
                !     $    ' ipbt_asv (number of Pitzer alpha parameters',/7x,'for ',
                !     $    ' any cation-anion or like pair. For the classical Pitzer',
                !     $    /7x,'data block organization present here, this variable',
                !     $    ' must have',/7x,'a value of 2.')
                !          stop
                nerr = nerr + 1
                go to 999
            end if
        end if

        if (jpdblo .eq. -1) then
            ! In the "classical" Pitzer data block organization, the E-lambda
            ! (E-theta) flag may be "on" or "off", as specified on the data
            ! file. Read and decode this flag.
            uelam = ' '
            read (nad1) uline
            uelam(1:8) = uline(17:24)
            if (uelam(1:3) .eq. 'off') then
                ielam = -1
            elseif (uelam(1:3) .eq. 'on ') then
                ielam = 0
            else
                j2 = ilnobl(uelam)
                !          write (noutpt,1010) uelam(1:j2)
                !          write (nttyo,1010) uelam(1:j2)
                ! 1010     format(/' * Error - (EQLIB/inupt) Have read an unrecognized',
                !     $    /7x,'value of "',a,'" for the E-lambda (E-theta) flag from',
                !     $    /7x,'the data file. Allowed values are "on" and "off".')
                !          stop
                nerr = nerr + 1
                go to 999
            end if
        else
            ! In the "new" Pitzer data block organization, the E-lambda flag is
            ! always "on".
            ielam = 0
        end if

        ! Read the species pairs for which S-lambda coefficients are defined.
        ! These data are comprised in two superblocks.
        ja = 0
        nsl = 0
        do nblock = 1,2
            ! Read a block.
            ! Read the names of the species in a pair.

            15   read (nad1) unam1,unam2

            ! Test for end of superblock.
            if (unam1(1:6) .eq. uendit(1:6)) go to 130

            ! Increment the S-lambda species pair counter.
            nsl = nsl + 1

            ! Calling sequence substitutions:
            !   narn1a for nrn1a
            !   narn2a for nrn2a
            !   unam1 for unam
            call srchn(narn1a,narn2a,ns,nsta_asv,unam1,uspeca)
            nslxa(1,nsl) = ns
            z1 = zchara(ns)

            ! Calling sequence substitutions:
            !   narn1a for nrn1a
            !   narn2a for nrn2a
            !   unam2 for unam
            call srchn(narn1a,narn2a,ns,nsta_asv,unam2,uspeca)
            nslxa(2,nsl) = ns
            z2 = zchara(ns)

            ! Read the temperature function coefficients for calculating
            ! Pitzer S-lambda(n) parameters. Read also the associated
            ! Pitzer alpha parameters.

            if (jpdblo .eq. -1) then
                ! Classical Pitzer data block organization.

                ! Read the lowest-order coefficients, which are here
                ! the 25C values of the corresponding interaction
                ! coefficients.
                read (nad1) (aslma(1,i,nsl), i = 0,2)

                ! Read the associated alpha coefficients.
                read (nad1) (alphai(i), i = 1,2)

                ! Read the higher-order coefficients, which here are
                ! first and second-order temperature derivatives.
                do i = 0,2
                    read (nad1) aslma(2,i,nsl),aslma(3,i,nsl)
                end do
            else
                ! New Pitzer data block organization.

                ! Read the associated alpha coefficients.
                if ((z1*z2) .lt. 0.) then
                    ! Read a larger set of data for cation-anion pairs.
                    do i = 1,ipbt_asv
                        read (nad1) ux16,alphai(i)
                    end do

                    do i = 0,ipbt_asv
                        read (nad1) ux16
                        do j = 1,jpfc_asv
                            read (nad1) aslma(j,i,nsl)
                        end do
                    end do
                else
                    ! Read a more limited set of data for all other pair types.
                    read (nad1) ux16
                    do j = 1,jpfc_asv
                        read (nad1) aslma(j,0,nsl)
                    end do
                end if
            end if

            ! Read the block terminator.
            read (nad1) uline(1:72)

            ! Test for alpha coefficient set already in the palpaa array.
            do j = 1,ja
                qx = .true.
                do i = 1,ipbt_asv
                    aax = abs(palpaa(i,j) - alphai(i))
                    if (aax .gt. 1.e-12) then
                        qx = .false.
                        go to 110
                    end if
                end do
                110     continue

                if (qx) then
                    ! Found the index to an existing alpha pair. Store this
                    ! index, then go process the data for another species pair.
                    nalpaa(nsl) = j
                    go to 15
                end if
            end do

            ! Not in the set; add it and store the index for this species pair.
            ja = ja + 1

            do i = 1,ipbt_asv
                palpaa(i,ja) = alphai(i)
            end do
            nalpaa(nsl) = ja

            ! Go process the data for another species pair.
            go to 15

            130   continue
        end do

        nslta = nsl
        napta = ja

        DEALLOCATE(alphai)

        ! Read the species triplets for which mu coefficients are
        ! defined. These data are comprised in two superblocks.

        nmu = 0
        do nblock = 1,2
            ! Read a block.

            ! Read the names of the species in a triplet.
            150   read (nad1) unam1,unam2,unam3

            ! Test for end of superblock.
            if (unam1(1:6) .eq. uendit(1:6)) go to 200


            ! Increment the mu species triplet counter.
            nmu = nmu + 1

            ! Calling sequence substitutions:
            !   narn1a for nrn1a
            !   narn2a for nrn2a
            !   unam1 for unam
            call srchn(narn1a,narn2a,ns,nsta_asv,unam1,uspeca)
            nmuxa(1,nmu) = ns

            ! Calling sequence substitutions:
            !   narn1a for nrn1a
            !   narn2a for nrn2a
            !   unam2 for unam
            call srchn(narn1a,narn2a,ns,nsta_asv,unam2,uspeca)
            nmuxa(2,nmu) = ns

            ! Calling sequence substitutions:
            !   narn1a for nrn1a
            !   narn2a for nrn2a
            !   unam3 for unam
            call srchn(narn1a,narn2a,ns,nsta_asv,unam3,uspeca)
            nmuxa(3,nmu) = ns

            ! Read the coefficients for calculating Pitzer mu parameters as a
            ! function of temperature.
            if (jpdblo .eq. -1) then

                ! Classical Pitzer data block organization.
                read (nad1) amua(1,nmu),amua(2,nmu),amua(3,nmu)
            else
                ! New Pitzer data block organization.
                read (nad1) ux16
                do j = 1,jpfc_asv
                    read (nad1) amua(j,nmu)
                enddo
            end if

            ! Read the block terminator.
            read (nad1) uline(1:72)

            go to 150

            200   continue
        end do

        nmuta = nmu
        999 continue
    end

    subroutine indatd(data1, arr, ipc, ipcx_asv, narxt, narx_asv, ntprt, ntpr_asv, ux24)
        implicit none
        integer ipcx_asv,narx_asv,ntpr_asv

        integer data1
        integer narxt(ntpr_asv)
        integer ipc, ntprt
        real*8 arr(narx_asv,ntpr_asv,ipcx_asv)
        character*24 ux24

        integer n, ntpr

        read (data1) ux24
        do ntpr = 1, ntprt
            read (data1) (arr(n,ntpr,ipc), n = 1,narxt(ntpr))
        end do
    end

    ! This subroutine reads a superblock of species blocks from the supporting
    ! data file "data1".
    subroutine indats(adhfsa, advfsa, axhfsa, axlksa, axvfsa, cdrsa, cdrsv, cessa, &
                      cessv, ipch, ipch_asv, ipcv, ipcv_asv, mwtspa, nad1, narxt, &
                      narx_asv, nata, nbta, nbta_asv, nbta1_asv, nbtafd, &
                      ncmpra, ncta, ncta_asv, ndrsa, ndrsa_asv, ndrsn, ndrsra, &
                      nerr, nessa, nessa_asv, nessn, nessra, ngta, nlta, &
                      nmta, np, npta_asv, ns, nsta_asv, ntprt, &
                      ntpr_asv, uaqsln, ubasp, udrsv, uelema, uendit, uessv, &
                      uphasa, uphasv, uptgas, uptliq, uptsld, uptypa, usblkf, &
                      uspeca, vosp0a, zchara)

        implicit none
        integer ipch_asv,ipcv_asv,narx_asv,nbta_asv,nbta1_asv
        integer ncta_asv,ndrsa_asv,nessa_asv,npta_asv
        integer nsta_asv,ntpr_asv

        integer narxt(ntpr_asv),ncmpra(2,npta_asv),ndrsa(ndrsa_asv)
        integer ndrsra(2,nsta_asv),nessa(nessa_asv),nessra(2,nsta_asv)

        integer ipch,ipcv,nad1,nata,nbta,nbtafd,ncta,ndrsn,nerr
        integer nessn,ngta,nlta,nmta,np,ns,ntprt

        character*48 ubasp(nbta_asv),uspeca(nsta_asv)
        character*24 udrsv(nbta1_asv),uphasa(npta_asv),uptypa(npta_asv)
        character*24 uphasv,uaqsln,uptsld,uptliq,uptgas,usblkf
        character*8 uelema(ncta_asv),uessv(ncta_asv)
        character*8 uendit

        real*8 adhfsa(narx_asv,ntpr_asv,ipch_asv,nsta_asv)
        real*8 advfsa(narx_asv,ntpr_asv,ipcv_asv,nsta_asv)
        real*8 axhfsa(narx_asv,ntpr_asv,nsta_asv)
        real*8 axlksa(narx_asv,ntpr_asv,nsta_asv)
        real*8 axvfsa(narx_asv,ntpr_asv,nsta_asv),cdrsa(ndrsa_asv)
        real*8 cdrsv(nbta1_asv),cessa(nessa_asv),cessv(ncta_asv)
        real*8 mwtspa(nsta_asv),vosp0a(nsta_asv),zchara(nsta_asv)

        integer ipc,j2,j3,j4,j5,j6,j7,n,nb,nc,nctsv,ndrstv,nf,ntpr

        character*24 uelect,uhx,uspecv,ux24

        data uelect /'e-                      '/

        100 continue

        ! Read a species block.
        !   uspecv = species name
        !   nctsv  = number of chemical elements comprising the species
        !   ndrstv = number of reaction coefficients in the reaction
        !          associated with the species
        read (nad1) uspecv,nctsv,ndrstv
        j2 = ilnobl(uspecv)
        j5 = ilnobl(usblkf)

        ! Check for the end of the current superblock.
        if (uspecv(1:8) .eq. uendit(1:8)) go to 999

        ! If the species is a pure mineral or pure liquid, set the phase name to
        ! match the species name.
        if (usblkf(1:24).eq.uptsld(1:24) .or. usblkf(1:24).eq.uptliq(1:24)) then
            uphasv(1:24) = uspecv(1:24)
        end if
        j3 = ilnobl(uphasv)

        ! Have another species.
        ns = ns + 1

        ! Load the species name array. Note that the last 24 characters contain the
        ! name of the associated phase.
        uspeca(ns)(1:24) = uspecv(1:24)
        uspeca(ns)(25:48) = uphasv(1:24)

        ! mwtspa = molecular weight
        ! zchara = electrical charge
        ! vosp0a = molar volume (not read).
        read (nad1) mwtspa(ns),zchara(ns)
        vosp0a(ns) = 0.

        ! cessv  = chemical element stoichiometric coefficient
        ! uessv  = name of corresponding chemical element.
        if (nctsv .gt. 0) read (nad1) (cessv(n),uessv(n), n = 1,nctsv)

        ! Decode the elemental composition.
        nessra(1,ns) = nessn + 1
        if (nctsv .gt. 0) then
            do n = 1,nctsv
                do nc = 1,ncta
                    if (uessv(n)(1:8) .eq. uelema(nc)(1:8)) then
                        nessn = nessn + 1
                        cessa(nessn) = cessv(n)
                        nessa(nessn) = nc
                        go to 120
                    end if
                end do
                j4 = ilnobl(uessv(n))
                !          write (noutpt,1010) uspecv(1:j2),uphasv(1:j3),usblkf(1:j5),
                !     $    uessv(n)(1:j4)
                !          write (nttyo,1010) uspecv(1:j2),uphasv(1:j3),usblkf(1:j5),
                !     $    uessv(n)(1:j4)
                ! 1010     format(/' * Error - (EQLIB/indats) The species',
                !     $    /7x,a,' (',a,')',
                !     $    /7x,'appearing on the data file in the ',a,' superblock',
                !     $    /7x,'is listed as being composed of an unrecognized',
                !     $    /7x,'chemical element ',a,'.')
                nerr = nerr + 1
                120  continue
            end do
            nessra(2,ns) = nessn
        else
            ! Have a species comprised of no chemical elements. This is permitted
            ! only for the following:
            !   O2(g) in a phase other than "gas"
            !   e-    in any phase
            if (uspecv(1:5) .eq. 'O2(g)') then
                if (usblkf(1:24) .eq. uptgas(1:24)) then
                    !            write (noutpt,1020) uspecv(1:j2),uphasv(1:j3),usblkf(1:j5)
                    !            write (nttyo,1020) uspecv(1:j2),uphasv(1:j3),usblkf(1:j5)
                    ! 1020       format(/' * Error - (EQLIB/indats) The species',
                    !     $      /7x,a,' (',a,')',
                    !     $      /7x,'appearing on the data file in the ',a,' superblock',
                    !     $      /7x,'is comprised of no chemical elements.')
                    nerr = nerr + 1
                end if
            else if (uspecv(1:2) .eq. uelect(1:2)) then
                continue
            else
                ! write (noutpt,1020) uspecv(1:j2),uphasv(1:j3),usblkf(1:j5)
                ! write (nttyo,1020) uspecv(1:j2),uphasv(1:j3),usblkf(1:j5)
                ! nerr = nerr + 1
            end if

            ! A species with no elements is treated as being comprised of one "null"
            ! element.
            nessn = nessn + 1
            cessa(nessn) = 0.
            nessa(nessn) = 0
            nessra(2,ns) = nessn
        end if

        ! Read the associated reaction data, if any.

        ! Read the reaction, if any.
        if (ndrstv .gt. 0) then
            read (nad1) (cdrsv(n),udrsv(n), n = 1,ndrstv)
        endif

        ! Decode the associated reaction into a temporary format. The species
        ! associated with the reaction is moved if necessary so that it is the first
        ! species to appear in the reaction. Its species index is stored in the
        ! ndrsa array. The other species are presumed to be basis species. If one
        ! of these species has not been already loaded into the ubasp array, it is
        ! loaded at this time. The basis number of the species is stored in the
        ! ndrsa array. It will be converted to the corresponding species number
        ! after all species are loaded. This scheme permits the loading of a
        ! reaction which is written in terms of a basis species which itself has not
        ! yet been loaded.
        ndrsra(1,ns) = ndrsn + 1
        if (ndrstv .le. 0) then
            ! A species with no reaction listed on the data file is treated as a
            ! basis species. An associated reaction with one "null" species is
            ! created. The actual reaction is formally treated as one in which one
            ! mole of the associated species is destroyed and one mole of the same
            ! species is created. This is termed an "identity reaction." However,
            ! the reaction stored is not the identity reaction but the one with the
            ! "null" species as the only species.
            nbta = nbta + 1
            ubasp(nbta) = uspeca(ns)
            ndrsn = ndrsn + 1
            cdrsa(ndrsn) = 0.
            ndrsa(ndrsn) = 0
            ndrsra(2,ns) = ndrsn
            do ntpr = 1,ntpr_asv
                do n = 1,narx_asv
                    axlksa(n,ntpr,ns) = 0.
                end do
            end do
        else if (ndrstv .eq. 1) then
            !        write (noutpt,1030) uspecv(1:j2),uphasv(1:j3),usblkf(1:j5)
            !        write (nttyo,1030) uspecv(1:j2),uphasv(1:j3),usblkf(1:j5)
            ! 1030   format(/' * Error - (EQLIB/indats) The species'
            !     $  /7x,a,' (',a,')',
            !     $  /7x,'appearing on the data file in the ',a,' superblock',
            !     $  /7x,'has a reaction with only one species in it.')
            nerr = nerr + 1
        else
            ! Make sure that the species associated with the reaction is the first
            ! species in the reaction.
            do n = 1,ndrstv
                if (udrsv(n)(1:24) .eq. uspecv(1:24)) then
                    ndrsn = ndrsn + 1
                    cdrsa(ndrsn) = cdrsv(n)
                    ndrsa(ndrsn) = ns
                    go to 160
                end if
            end do

            !        write (noutpt,1040) uspecv(1:j2),uphasv(1:j3),usblkf(1:j5)
            !        write (nttyo,1040) uspecv(1:j2),uphasv(1:j3),usblkf(1:j5)
            ! 1040   format(/' * Error - (EQLIB/indats) The species',
            !     $  /7x,a,' (',a,')',
            !     $  /7x,'appearing on the data file in the ',a,' superblock',
            !     $  /7x,'does not appear in its associated reaction.')
            !        j4 = ilnobl(udrsv(1))
            !        write (noutpt,1050) udrsv(1)(1:j4),uphasv(1:j3),uspecv(1:j2),
            !     $  uphasv(1:j3)
            !        write (nttyo,1050) udrsv(1)(1:j4),uphasv(1:j3),uspecv(1:j2),
            !     $  uphasv(1:j3)
            ! 1050   format(/9x,'Is ',a,' (',a,') a doppelganger of',
            !     $  /12x,a,' (',a,')?')
            udrsv(1) = uspecv
            nerr = nerr + 1

            160   nf = 0

            do n = 1,ndrstv
                if (udrsv(n)(1:24).eq.uspecv(1:24) .and. nf.eq.0) then
                    nf = 1
                    if (ns .le. nbtafd) then
                        ! The species is in the range of aqueous species that are
                        ! intended to be basis species. Add it to the basis set.
                        nbta = nbta + 1
                        ubasp(nbta) = udrsv(n)
                    end if
                else
                    ndrsn = ndrsn + 1
                    cdrsa(ndrsn) = cdrsv(n)
                    do nb = 1,nbta
                        if (ubasp(nb)(1:24) .eq. udrsv(n)(1:24)) then
                            ndrsa(ndrsn) = nb
                            go to 180
                        end if
                    end do

                    ! The reaction is written in terms of another species that is
                    ! not yet in the basis set. Add it to that set.
                    nbta = nbta + 1
                    ubasp(nbta) = udrsv(n)
                    ndrsa(ndrsn) = nbta
                end if
                180  continue
            end do

            ndrsra(2,ns) = ndrsn

            ! Read the interpolating polynomial coefficients for the log K of the
            ! reaction.
            read (nad1) ux24
            j6 = ilnobl(ux24)
            uhx = 'Log K'
            j7 = ilnobl(uhx)
            if (uhx(1:j7) .ne. ux24(1:j6)) then
                !          write (noutpt,1052) ux24(1:j6),uhx(1:j7)
                !          write (nttyo,1052) ux24(1:j6),uhx(1:j7)
                ! 1052     format(/' * Error - (EQLIB/indats) Have read the tag',
                !     $    ' string "',a,'"',/7x,'where "',a,'" was expected.')
                nerr = nerr + 1
            end if
            do ntpr = 1,ntprt
                read (nad1) (axlksa(n,ntpr,ns), n = 1,narxt(ntpr))
            end do
        end if

        if (ipch .ge. 0) then
            ! Read the interpolating polynomial coefficients for the enthalpy
            ! function and its pressure derivatives. For a basis species, the
            ! enthalpy function is the standard partial molar enthalpy of formation;
            ! for all other species, the enthalpy function is the standard partial
            ! molar enthalpy of reaction.
            read (nad1) ux24
            j6 = ilnobl(ux24)
            uhx = 'Enthalpy'
            j7 = ilnobl(uhx)
            if (uhx(1:j7) .ne. ux24(1:j6)) then
                ! write (noutpt,1052) ux24(1:j6),uhx(1:j7)
                ! write (nttyo,1052) ux24(1:j6),uhx(1:j7)
                nerr = nerr + 1
            end if
            do ntpr = 1,ntprt
                read (nad1) (axhfsa(n,ntpr,ns), n = 1,narxt(ntpr))
            end do
            do ipc = 1,ipch
                read (nad1) ux24
                j6 = ilnobl(ux24)
                if (ipc .eq. 1) then
                    uhx = 'dEnthalpy/dP'
                else
                    uhx = 'd( )Enthalpy/dP( )'
                    write (uhx(3:3),'(i1)') ipc,ipc
                    write (uhx(17:17),'(i1)') ipc,ipc
                end if
                j7 = ilnobl(uhx)
                if (uhx(1:j7) .ne. ux24(1:j6)) then
                    ! write (noutpt,1052) ux24(1:j6),uhx(1:j7)
                    ! write (nttyo,1052) ux24(1:j6),uhx(1:j7)
                    nerr = nerr + 1
                end if
                do ntpr = 1,ntprt
                    read (nad1) (adhfsa(n,ntpr,ipc,ns), n = 1,narxt(ntpr))
                end do
            end do
        end if

        if (ipcv .ge. 0) then
            ! Read the interpolating polynomial coefficients for the volume function
            ! and its pressure derivatives. For a basis species, the volume function
            ! is the standard partial molar enthalpy of formation; for all other
            ! species, the volume function is the standard partial molar volume
            ! of reaction.
            read (nad1) ux24
            j6 = ilnobl(ux24)
            uhx = 'Volume'
            j7 = ilnobl(uhx)
            if (uhx(1:j7) .ne. ux24(1:j6)) then
                ! write (noutpt,1052) ux24(1:j6),uhx(1:j7)
                ! write (nttyo,1052) ux24(1:j6),uhx(1:j7)
                nerr = nerr + 1
            end if
            do ntpr = 1,ntprt
                read (nad1) (axvfsa(n,ntpr,ns), n = 1,narxt(ntpr))
            end do
            do ipc = 1,ipcv
                read (nad1) ux24
                j6 = ilnobl(ux24)
                if (ipc .eq. 1) then
                    uhx = 'dVolume/dP'
                else
                    uhx = 'd( )Volume/dP( )'
                    write (uhx(3:3),'(i1)') ipc,ipc
                    write (uhx(15:15),'(i1)') ipc,ipc
                end if
                j7 = ilnobl(uhx)
                if (uhx(1:j7) .ne. ux24(1:j6)) then
                    ! write (noutpt,1052) ux24(1:j6),uhx(1:j7)
                    ! write (nttyo,1052) ux24(1:j6),uhx(1:j7)
                    nerr = nerr + 1
                end if
                do ntpr = 1,ntprt
                    read (nad1) (advfsa(n,ntpr,ipc,ns), n = 1,narxt(ntpr))
                end do
            end do
        end if

        if (usblkf(1:24) .eq. uaqsln(1:24)) nata = nata + 1
 
        if (usblkf(1:24) .eq. uptsld(1:24)) then
            nmta = nmta + 1
            np = np + 1
            uphasa(np) = uspecv
            uptypa(np) = uptsld
            ncmpra(1,np) = ns
            ncmpra(2,np) = ns
        end if

        if (usblkf(1:24) .eq. uptliq(1:24)) then
            nlta = nlta + 1
            np = np + 1
            uphasa(np) = uspecv
            uptypa(np) = uptliq
            ncmpra(1,np) = ns
            ncmpra(2,np) = ns
        end if

        if (usblkf(1:24) .eq. uptgas(1:24)) ngta = ngta + 1

        ! Loop back to read another species block.
        go to 100

        999 continue
    end

    subroutine indatc(data1, arr, narx_asv, narxt, ntpr_asv, ntprt, ux24)
        implicit none

        integer, intent(in) :: data1

        integer narx_asv, ntpr_asv
        integer narxt(ntpr_asv)
        integer ntprt
        real*8 arr(narx_asv,ntpr_asv)
        character*24 ux24
        integer n, ntpr

        read (data1) ux24
        do ntpr = 1,ntprt
            read (data1) (arr(n,ntpr), n = 1,narxt(ntpr))
        enddo
    end

    ! This subroutine clones the nsc-th species into the ns-th. The ns-th species
    ! belongs to the np-th phase. Typically, the nsc-th species is a pure mineral or
    ! liquid and the ns-th species is the corresponding component species of a solid
    ! or liquid solution.
    subroutine clones(axlksa, cdrsa, cessa, mwtspa, narx_asv, ndrsa, ndrsa_asv, &
                      ndrsn, ndrsra, nessa, nessa_asv, nessn, nessra, np, &
                      npta_asv, ns, nsc, nsta_asv, ntpr_asv, uphasa, uspeca, zchara)

        implicit none
        integer narx_asv,ndrsa_asv,nessa_asv,npta_asv,nsta_asv,ntpr_asv

        integer ndrsa(ndrsa_asv)
        integer ndrsra(2,nsta_asv)
        integer nessa(nessa_asv)
        integer nessra(2,nsta_asv)

        integer ndrsn,nessn,np,ns,nsc

        character*24 uphasa(npta_asv)
        character*48 uspeca(nsta_asv)

        real*8 axlksa(narx_asv,ntpr_asv,nsta_asv),cessa(nessa_asv)
        real*8 cdrsa(ndrsa_asv),mwtspa(nsta_asv),zchara(nsta_asv)

        integer i,j,ndrsn1,nessn1,nr1,nr2,nse,nt

        ! Copy the name, molecular weight, and electrical charge.
        ! Note that the phase part of the name is different.
        uspeca(ns)(1:24) = uspeca(nsc)(1:24)
        uspeca(ns)(25:48) = uphasa(np)(1:24)
        mwtspa(ns) = mwtspa(nsc)
        zchara(ns) = zchara(nsc)

        ! Copy the elemental composition.
        nessra(1,ns) = nessn + 1
        nr1 = nessra(1,nsc)
        nr2 = nessra(2,nsc)
        do nessn1 = nr1,nr2
            nessn = nessn + 1
            cessa(nessn) = cessa(nessn1)
            nessa(nessn) = nessa(nessn1)
        end do
        nessra(2,ns) = nessn

        ! Copy the associated reaction.
        ndrsra(1,ns) = ndrsn + 1
        nr1 = ndrsra(1,nsc)
        nr2 = ndrsra(2,nsc)
        nt = nr2 - nr1 + 1
        if (nt .lt. 2) then
            ! The nsc-th species is a data file basis species that has only an
            ! identity reaction. Write a linking reaction.
            ndrsn = ndrsn + 1
            cdrsa(ndrsn) = -1.
            ndrsa(ndrsn) = ns
            ndrsn = ndrsn + 1
            cdrsa(ndrsn) = 1.
            ndrsa(ndrsn) = nsc
        else
            ! The nsc-th species has a reaction which can be copied.
            do ndrsn1 = nr1,nr2
                ndrsn = ndrsn + 1
                cdrsa(ndrsn) = cdrsa(ndrsn1)
                nse = ndrsa(ndrsn1)
                if (nse .eq. nsc) nse = ns
                ndrsa(ndrsn) = nse
            end do
        end if
        ndrsra(2,ns) = ndrsn

        ! Copy the coefficients of the polynomials which represent the thermodynamic
        ! functions of the reaction. Note that this is valid whether the reaction
        ! is an identity reaction or a real one.
        do j = 1,ntpr_asv
            do i = 1,narx_asv
              axlksa(i,j,ns) = axlksa(i,j,nsc)
            end do
        end do
    end

    ! This subroutine decodes the ubasp array (list of basis species names built
    ! while reading the data file). It puts their species indices in the nbaspa
    ! array. The basis indices that were put in the ndrsa array are replaced by
    ! the corresponding species indices. The working basis set may be subsequently
    ! expanded when the input file is interpreted, as any species on the input file
    ! that is referenced as a basis species is added to that set if not already in it.
    subroutine dfbasp(nbaspa, nbta, nbta_asv, ndrsa, ndrsa_asv, ndrsra, nerr, &
                      nsta, nsta_asv, ubasp, uspeca)
        implicit none
        integer nbta_asv, ndrsa_asv, nsta_asv
        integer nbaspa(nbta_asv),ndrsa(ndrsa_asv),ndrsra(2,nsta_asv)
        integer nbta,nerr,nsta
        character*48 ubasp(nbta_asv),uspeca(nsta_asv)
        integer jlen,n,nb,ns,nr1,nr1p1,nr2,nt
        character*56 uspn56
        ! Set up the nbaspa array and expand the elements of the ubasp array to the
        ! full 48 characters.
        do nb = 1,nbta
            do ns = 1,nsta
                if (uspeca(ns)(1:24) .eq. ubasp(nb)(1:24)) then
                    nbaspa(nb) = ns
                    ubasp(nb)(1:48) = uspeca(ns)(1:48)
                    go to 105
              end if
            end do

            nbaspa(nb) = 0

            ! Calling sequence substitutions:
            !     ubasp(nb) for unam48

            call fmspnm(jlen,ubasp(nb),uspn56)
     !        write (noutpt,1000) uspn56(1:jlen)
     !        write (nttyo,1000) uspn56(1:jlen)
     ! 1000   format(/" * Error - (EQLIB/dfbasp) Couldn't find a basis",
     !     $  ' species named',/7x,a,' among the species read from the',
     !     $  ' data file.',/7x,'It must be referenced erroneously in',
     !     $  ' the associated reaction',/7x,'for another species.')
            nerr = nerr + 1
      105   continue
        end do
        ! Convert basis species indices in the ndrsa array to species indices.
        do ns = 1,nsta
            nt = ndrsra(2,ns) - ndrsra(1,ns) + 1
            if (nt .ge. 2) then
                nr1 = ndrsra(1,ns)
                nr1p1 = nr1 + 1
                nr2 = ndrsra(2,ns)
                do n = nr1p1,nr2
                    nb = ndrsa(n)
                    ndrsa(n) = nbaspa(nb)
              end do
          end if
        end do
    end

    ! This subroutine formats a 48-character species name (unam48) into a
    ! 56-character string (uspn56) so that the phase part of the name (in the field
    ! composed of the second 24 characters) appears in parentheses following the
    ! actual species part (in the field composed of the first 24 characters). For
    ! example, ignoring trailing blanks, "Albite                  Plagioclase     "
    ! is reformatted as "Albite (Plagioclase)". However, the phase part (including
    ! the surrounding parentheses) is omitted from the formatted string if the phase
    ! name is not present in the 48-character string or if the phase name is
    ! identical to the species name. Thus, the returned string for pure Albite is
    ! 'Albite', not 'Albite (Albite)'.
    !
    ! The formatted string is used mostly in error, warning, and note messages
    ! written by EQ3NR and EQ6.
    !
    ! This subroutine is similar to fmspnx.f. However, that subroutine omits the
    ! phase part if the phase name is 'Aqueous solution'.
    subroutine fmspnm(jlen, unam48, uspn56)
        implicit none

        integer jlen

        character*48 unam48
        character*56 uspn56

        integer j2

        ! integer ilnobl

        character*24 uphnam

        uspn56 = unam48(1:24)
        jlen = ilnobl(uspn56)

        uphnam = unam48(25:48)
        j2 = ilnobl(uphnam)
        if (uphnam(1:24) .ne. unam48(1:24)) then
            if (j2 .gt. 0) then
                uspn56(jlen + 1:jlen + 2) = ' ('
                uspn56(jlen + 3:jlen + 2 + j2) = uphnam(1:j2)
                jlen = jlen + 3 + j2
                uspn56(jlen:jlen) = ')'
            end if
         end if
    end
end
