#!/usr/bin/env groovy

pipeline {

    agent {
        // Use the docker to assign the Python version.
        docker {
            alwaysPull true
            image 'lsstts/develop-env:develop'
            args "-u root --entrypoint=''"
        }
        
    }

    environment {
        // Use the double quote instead of single quote
        // XML report path
        DEV_TOOL="/opt/rh/devtoolset-8/enable"
        LSST_STACK="/opt/lsst/software/stack"
        XML_REPORT="jenkinsReport/report.xml"
        MODULE_NAME="lsst.ts.cbp"
        user_ci = credentials('lsst-io')
        LTD_USERNAME="${user_ci_USR}"
        LTD_PASSWORD="${user_ci_PSW}"
        work_branches = "${GIT_BRANCH} ${CHANGE_BRANCH} develop"

    }

    stages {
        stage ('Install Requirements And Update Branches') {
            steps {
                // When using the docker container, we need to change
                // the HOME path to WORKSPACE to have the authority
                // to install the packages.
                withEnv(["WHOME=${env.WORKSPACE}"]) {
                    sh """
                        source /home/saluser/.setup_dev.sh || echo loading env failed. Continuing...
                        cd /home/saluser/repos/ts_xml
                        /home/saluser/.checkout_repo.sh ${work_branches}
                        git pull
                        cd /home/saluser/repos/ts_salobj
                        /home/saluser/.checkout_repo.sh ${work_branches}
                        git pull
                        cd /home/saluser/repos/ts_sal
                        /home/saluser/.checkout_repo.sh ${work_branches}
                        git pull
                        cd /home/saluser/repos/ts_idl
                        /home/saluser/.checkout_repo.sh ${work_branches}
                        git pull
                        cd /home/saluser/repos/ts_config_mtcalsys
                        /home/saluser/.checkout_repo.sh ${work_branches}
                        git pull
                        make_idl_files.py CBP
                    """
                }
            }
        }

        stage('Unit Tests with Coverage') {
            steps {
                // Direct the HOME to WORKSPACE for pip to get the
                // installed library.
                // 'PATH' can only be updated in a single shell block.
                // We can not update PATH in 'environment' block.
                // Pytest needs to export the junit report.
                withEnv(["WHOME=${env.WORKSPACE}"]) {
                    sh """
                        source /home/saluser/.setup_dev.sh || echo loading env failed. Continuing...
                        export TS_CONFIG_MTCALSYS_DIR=/home/saluser/repos/ts_config_mtcalsys
                        pip install .[dev]
                        pytest --cov-report html --cov=${env.MODULE_NAME} --junitxml=${env.XML_REPORT}
                    """
                }
            }
        }
        stage('Build and Upload Documentation') {
            steps {
                withEnv(["WHOME=${env.WORKSPACE}"]) {
                    sh """
                    source /home/saluser/.setup_dev.sh || echo loading env failed. Continuing...
                    pip install .[dev]
                    package-docs build
                    ltd upload --product ts-cbp --git-ref ${GIT_BRANCH} --dir doc/_build/html
                    """
                }
            }
        }
    }

    post {
        always {
            withEnv(["HOME=${env.WORKSPACE}"]) {
                sh 'chown -R 1003:1003 ${HOME}/'
            }
            // The path of xml needed by JUnit is relative to
            // the workspace.
            junit 'jenkinsReport/*.xml'

            // Publish the HTML report
            publishHTML(target: [
                allowMissing: false,
                alwaysLinkToLastBuild: false,
                keepAll: true,
                reportDir: 'htmlcov',
                reportFiles: 'index.html',
                reportName: "Coverage Report"
              ])
        }

        cleanup {
            // clean up the workspace
            deleteDir()
        }
    }
}